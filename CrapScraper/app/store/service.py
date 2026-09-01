from __future__ import annotations

import os
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.store.bundles import StoreBundleService
from app.store.monitor import StoreMonitorService
from app.store.pricing import StorePricingService, period
from app.store.quality import StoreQualityService
from app.store.repository import StoreRepository
from app.store.woocommerce import FixtureStoreGateway, StoreWooCommerceGateway, is_pack, is_plan, product_kind
from app.store.wordpress import FixtureManualQueue, WordPressManualQueueClient


def enabled(name):
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def folded(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    return " ".join(text.split())


class StoreService:
    def __init__(self, data_dir: Path, updates, *, repository=None, gateway=None, queue=None):
        fixture = enabled("SCRAPER_STORE_E2E_FIXTURES")
        self.repository = repository or StoreRepository(data_dir)
        self.gateway = gateway or (FixtureStoreGateway() if fixture else StoreWooCommerceGateway())
        self.queue = queue or (FixtureManualQueue() if fixture else WordPressManualQueueClient())
        self.updates = updates
        self.monitor_service = StoreMonitorService(self.repository, self.queue, updates)
        self.write_enabled = enabled("SCRAPER_STORE_WRITE_ENABLED")
        self.pricing = StorePricingService(self.gateway, self.repository, self.write_enabled)
        self.bundles_service = StoreBundleService(self.gateway)
        self.quality_service = StoreQualityService()
        self._cache = []
        self._cached_at = 0.0
        self._issues = []
        self._issues_at = 0.0
        self._quality_complete = False
        self._quality_worker = None
        self._quality_error = ""
        self._variation_cache = {}
        self._variation_cached_at = {}
        self.lock = threading.RLock()

    def _products(self, refresh=False):
        with self.lock:
            if refresh or not self._cache or time.monotonic() - self._cached_at > 60:
                self._cache = list(self.gateway.products(status="publish", _fields="id,name,type,status,categories,short_description,meta_data,images,regular_price,sale_price"))
                self._cached_at = time.monotonic()
            return list(self._cache)

    def _quality(self):
        with self.lock:
            if self._quality_complete and time.monotonic() - self._issues_at <= 300:
                return list(self._issues)
        products = self._products()
        variable = [product for product in products if str(product.get("type")) == "variable"]
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(variable)))) as executor:
            variations = dict(zip((int(product["id"]) for product in variable), executor.map(lambda product: self._variations(product["id"]), variable)))
        issues = self.quality_service.inspect(products, variations_by_product=variations)
        with self.lock:
            self._issues = issues
            self._issues_at = time.monotonic()
            self._quality_complete = True
            self._quality_error = ""
        return list(issues)

    def _start_quality_analysis(self):
        with self.lock:
            if self._quality_complete and time.monotonic() - self._issues_at <= 300:
                return
            if self._quality_worker and self._quality_worker.is_alive():
                return

            def run():
                try:
                    self._quality()
                except Exception as exc:
                    with self.lock:
                        self._quality_error = str(exc)

            self._quality_worker = threading.Thread(target=run, name="store-quality-analysis", daemon=True)
            self._quality_worker.start()

    def _variations(self, product_id):
        product_id = int(product_id)
        with self.lock:
            cached = self._variation_cache.get(product_id)
            cached_at = self._variation_cached_at.get(product_id, 0.0)
            if cached is not None and time.monotonic() - cached_at <= 300:
                return list(cached)
        rows = list(self.gateway.variations(product_id))
        with self.lock:
            self._variation_cache[product_id] = rows
            self._variation_cached_at[product_id] = time.monotonic()
        return list(rows)

    def summary(self):
        products = self._products()
        counts = {
            "products": len(products),
            "plugins": sum(product_kind(item) == "plugin" for item in products),
            "themes": sum(product_kind(item) == "theme" for item in products),
            "packs": sum(is_pack(item) for item in products),
        }
        return {"ok": True, "counts": counts, "monitor": self.monitor_service.snapshot()}

    def environment(self, check=False):
        method = getattr(self.updates, "verify_environment" if check else "environment", None)
        shared = method() if callable(method) else {"checks": []}
        woo = next((item for item in shared.get("checks", []) if item.get("key") == "woocommerce"), None)
        checks = []
        if woo:
            checks.append(woo)
        else:
            configured = bool(getattr(self.gateway, "base", "") and all(getattr(self.gateway, "auth", ())))
            checks.append({"key": "woocommerce", "label": "WooCommerce", "state": "attention" if configured else "blocked", "value": "CONFIGURADO / NÃO VALIDADO" if configured else "NÃO CONFIGURADO", "detail": "Use Verificar ambiente para confirmar a leitura autenticada."})
        checks.extend([
            {"key": "store_write", "label": "Escrita de preços", "state": "ok" if self.write_enabled else "blocked", "value": "HABILITADA" if self.write_enabled else "DESABILITADA", "detail": "Controlada por SCRAPER_STORE_WRITE_ENABLED."},
            {"key": "wordpress_monitor", "label": "Monitor WordPress", "state": "ok" if self.queue.configured else "attention", "value": "CONFIGURADO" if self.queue.configured else "NÃO CONFIGURADO", "detail": "Usa o contrato HMAC persistente do MU-plugin."},
        ])
        return {"ok": True, "checks": checks, "attention_count": sum(item["state"] != "ok" for item in checks)}

    def list_products(self, payload):
        query = str(payload.get("query") or "").casefold()
        kind = str(payload.get("type") or "")
        category = str(payload.get("category") or "").casefold()
        page = max(1, int(payload.get("page") or 1))
        size = max(1, min(100, int(payload.get("page_size") or 5)))
        rows = []
        for product in self._products():
            product_type = product_kind(product)
            if query and query not in (str(product.get("id")) + " " + str(product.get("name"))).casefold():
                continue
            if kind and product_type != kind:
                continue
            if category and not any(category == str(item.get("id")) or category == str(item.get("name", "")).casefold() for item in product.get("categories", []) or []):
                continue
            rows.append({"product_id": int(product["id"]), "product_name": product.get("name", ""), "type": product_type, "status": product.get("status", ""), "categories": [item.get("name", "") for item in product.get("categories", []) or []], "short_description": bool(str(product.get("short_description") or "").strip()), "pack": is_pack(product)})
        rows.sort(key=lambda item: (folded(item["product_name"]), item["product_id"]))
        return {"ok": True, "items": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "page_size": size, "pages": max(1, (len(rows) + size - 1) // size)}

    def product(self, product_id):
        product = self.gateway.product(int(product_id))
        variations = self._variations(product_id) if str(product.get("type") or "").startswith("variable") else []
        return {"ok": True, "item": product, "variations": variations, "issues": [item for item in self.quality_service.inspect([product], variations_by_product={int(product_id): variations}) if item["product_id"] == int(product_id)]}

    def categories(self):
        return {"ok": True, "items": self.gateway.categories()}

    def bundles(self):
        return {"ok": True, "items": self.bundles_service.list(self._products(), "pack")}

    def plans(self):
        return {"ok": True, "items": self.bundles_service.list(self._products(), "plan")}

    def pricing_catalog(self):
        products = self._products()
        individual = []
        sampled = {"plugin": 0, "theme": 0}
        for product in products:
            kind = product_kind(product)
            if kind not in sampled or sampled[kind] >= 6:
                continue
            variations = self._variations(product["id"]) if product.get("type") == "variable" else []
            accepted = False
            for variation in variations:
                billing = period(variation)
                if not billing:
                    continue
                accepted = True
                individual.append({"product_id": int(product["id"]), "product_name": str(product.get("name") or ""), "kind": kind, "variation_id": int(variation["id"]), "period": billing, "regular_price": str(variation.get("regular_price") or ""), "sale_price": str(variation.get("sale_price") or "")})
            if accepted:
                sampled[kind] += 1
        available = {kind: sum(product_kind(product) == kind for product in products) for kind in sampled}
        return {"ok": True, "write_enabled": self.write_enabled, "individual": {"items": individual, "total": len(individual), "sampled_products": sampled, "available_products": available}, "packs": {"items": self.bundles_service.list(products, "pack")}, "plans": {"items": self.bundles_service.list(products, "plan")}}

    def quality(self, payload):
        query = str(payload.get("query") or "").casefold()
        code = str(payload.get("code") or "")
        page = max(1, int(payload.get("page") or 1))
        size = max(1, min(100, int(payload.get("page_size") or 5)))
        if isinstance(self.gateway, FixtureStoreGateway):
            rows, complete, error = self._quality(), True, ""
        else:
            products = self._products()
            base = self.quality_service.inspect(products, check_variations=False)
            self._start_quality_analysis()
            with self.lock:
                complete, error = self._quality_complete, self._quality_error
                rows = list(self._issues) if complete else base
        rows = [item for item in rows if (not query or query in (str(item["product_id"]) + " " + item["product_name"]).casefold()) and (not code or item["code"] == code)]
        return {"ok": True, "items": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "page_size": size, "pages": max(1, (len(rows) + size - 1) // size), "analysis_complete": complete, "analysis_error": error}

    @staticmethod
    def _category_issue(product):
        names = [str(item.get("name") or "").strip() for item in product.get("categories", []) or [] if str(item.get("name") or "").strip()]
        generic = {"plugin", "plugins", "tema", "temas", "theme", "themes"}
        adequate = [name for name in names if folded(name) not in generic]
        if adequate:
            return None
        return {"code": "missing_categories", "field": "categories", "message": "Categoria funcional ausente; apenas tipo genérico informado." if names else "Produto sem categoria."}

    def quality_products(self, payload):
        products = self._products()
        if isinstance(self.gateway, FixtureStoreGateway):
            issues, complete, analysis_error = self._quality(), True, ""
        else:
            base = self.quality_service.inspect(products, check_variations=False)
            self._start_quality_analysis()
            with self.lock:
                complete, analysis_error = self._quality_complete, self._quality_error
                issues = list(self._issues) if complete else base
        by_product = {}
        for issue in issues:
            by_product.setdefault(int(issue["product_id"]), []).append(issue)
        rows = []
        for product in products:
            product_id = int(product["id"])
            meta = {str(item.get("key")): item.get("value") for item in product.get("meta_data", []) or []}
            problems = list(by_product.get(product_id, []))
            category_issue = self._category_issue(product)
            if category_issue:
                problems.append({"product_id": product_id, "product_name": product.get("name", ""), **category_issue})
            rows.append({
                "product_id": product_id,
                "product_name": str(product.get("name") or ""),
                "type": product_kind(product),
                "version": str(meta.get("pt_versao") or ""),
                "developer": str(meta.get("desenvolvedor") or ""),
                "official_url": str(meta.get("site_oficial") or ""),
                "short_description": str(product.get("short_description") or ""),
                "categories": [str(item.get("name") or "") for item in product.get("categories", []) or []],
                "problems": [{"code": item["code"], "field": item.get("field", ""), "message": item["message"]} for item in problems],
                "problem_codes": sorted({item["code"] for item in problems}),
            })
        query = folded(payload.get("query"))
        field = str(payload.get("field") or "")
        category = folded(payload.get("category"))
        status = str(payload.get("status") or "all")
        field_codes = {"version": "missing_version", "developer": "missing_developer", "official_url": "missing_official_url", "short_description": "missing_short_description", "categories": "missing_categories"}
        filtered = []
        for row in rows:
            haystack = folded(f"{row['product_id']} {row['product_name']}")
            if query and query not in haystack:
                continue
            if field and field_codes.get(field) not in row["problem_codes"]:
                continue
            if category and not any(category == folded(name) for name in row["categories"]):
                continue
            if status == "problems" and not row["problems"]:
                continue
            if status == "complete" and row["problems"]:
                continue
            filtered.append(row)
        filtered.sort(key=lambda item: (folded(item["product_name"]), item["product_id"]))
        page = max(1, int(payload.get("page") or 1))
        size = max(1, min(100, int(payload.get("page_size") or 10)))
        return {"ok": True, "items": filtered[(page - 1) * size:page * size], "total": len(filtered), "page": page, "page_size": size, "pages": max(1, (len(filtered) + size - 1) // size), "analysis_complete": complete, "analysis_error": analysis_error}

    def monitor(self):
        return {"ok": True, "monitor": self.monitor_service.snapshot()}

    def monitor_enable(self, value):
        return {"ok": True, "monitor": self.monitor_service.enable(value)}

    def monitor_run(self):
        return self.monitor_service.run(force=True)

    def pricing_preview(self, payload):
        return self.pricing.preview(payload, self._products())

    def pricing_apply(self, payload):
        result = self.pricing.apply(payload, self._products())
        self._cached_at = 0
        return result

    def bundle_preview(self, payload):
        return self.bundles_service.preview(payload)

    def bundle_apply(self, payload):
        result = self.bundles_service.apply(payload, self.write_enabled)
        self._cached_at = 0
        return result
