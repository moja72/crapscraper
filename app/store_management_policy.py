from __future__ import annotations

import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping

import app.store_pricing as pricing
import app.web as web
from app import settings

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_LIST_PACKS = pricing.list_store_pack_products
_BASE_UPDATE_PACK = pricing.update_store_pack_price
_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, Any] = {"at": 0.0, "products": []}
_CACHE_TTL_SECONDS = 180.0
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_unified_pricing.js"


def _kind_for_product(product: Mapping[str, Any]) -> str:
    if pricing.is_pack_product(product):
        return "pack"
    if pricing.product_matches_catalog_kind(product, "plugin"):
        return "plugin"
    if pricing.product_matches_catalog_kind(product, "theme"):
        return "theme"
    return ""


def _pair_summary(rows: list[Mapping[str, Any]], period: str) -> dict[str, Any]:
    matching = [row for row in rows if pricing.variation_period(row) == period]
    if not matching:
        return {"available": False, "regular_price": "", "sale_price": "", "mixed": False, "variation_count": 0}
    pairs = Counter(
        (str(row.get("regular_price", "") or ""), str(row.get("sale_price", "") or ""))
        for row in matching
    )
    pair, _count = pairs.most_common(1)[0]
    return {
        "available": True,
        "regular_price": pair[0],
        "sale_price": pair[1],
        "mixed": len(pairs) > 1,
        "variation_count": len(matching),
    }


def _load_unified_products(woo: Any) -> list[dict[str, Any]]:
    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE["products"] and now - float(_CACHE["at"] or 0) < _CACHE_TTL_SECONDS:
            return [dict(item) for item in _CACHE["products"]]

    fields = "id,name,type,status,categories,tags,attributes,regular_price,sale_price,price"
    products = [
        item for item in pricing._paged_products(woo, status="publish", _fields=fields)
        if isinstance(item, Mapping)
    ]
    selected = [(item, _kind_for_product(item)) for item in products]
    selected = [(item, kind) for item, kind in selected if kind]

    rows: list[dict[str, Any]] = []
    variable: list[tuple[Mapping[str, Any], str]] = []
    for product, kind in selected:
        product_id = int(product.get("id") or 0)
        if not product_id:
            continue
        if kind == "pack" or str(product.get("type", "")).strip().lower() != "variable":
            rows.append({
                "product_id": product_id,
                "product_name": str(product.get("name", "") or ""),
                "product_type": str(product.get("type", "") or ""),
                "kind": kind,
                "pricing_mode": "direct",
                "regular_price": str(product.get("regular_price", "") or ""),
                "sale_price": str(product.get("sale_price", "") or ""),
                "last_price": str(product.get("price", "") or ""),
                "annual": {"available": False, "regular_price": "", "sale_price": "", "mixed": False, "variation_count": 0},
                "lifetime": {"available": False, "regular_price": "", "sale_price": "", "mixed": False, "variation_count": 0},
            })
        else:
            variable.append((product, kind))

    def load_variations(item: tuple[Mapping[str, Any], str]) -> tuple[Mapping[str, Any], str, list[Mapping[str, Any]]]:
        product, kind = item
        data = list(woo.list_variations(
            int(product["id"]), per_page=100,
            _fields="id,name,sku,attributes,regular_price,sale_price",
        ) or [])
        return product, kind, [row for row in data if isinstance(row, Mapping)]

    workers = min(16, max(1, len(variable)))
    if variable:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="store-unified-prices") as executor:
            futures = [executor.submit(load_variations, item) for item in variable]
            for future in as_completed(futures):
                product, kind, variations = future.result()
                annual = _pair_summary(variations, "annual")
                lifetime = _pair_summary(variations, "lifetime")
                rows.append({
                    "product_id": int(product.get("id") or 0),
                    "product_name": str(product.get("name", "") or ""),
                    "product_type": str(product.get("type", "") or ""),
                    "kind": kind,
                    "pricing_mode": "variations" if annual["available"] or lifetime["available"] else "direct",
                    "regular_price": str(product.get("regular_price", "") or ""),
                    "sale_price": str(product.get("sale_price", "") or ""),
                    "last_price": str(product.get("price", "") or ""),
                    "annual": annual,
                    "lifetime": lifetime,
                })

    rows.sort(key=lambda item: (str(item.get("kind", "")), str(item.get("product_name", "")).casefold()))
    with _CACHE_LOCK:
        _CACHE["at"] = time.monotonic()
        _CACHE["products"] = [dict(item) for item in rows]
    return rows


def _invalidate_cache() -> None:
    with _CACHE_LOCK:
        _CACHE["at"] = 0.0
        _CACHE["products"] = []


def _unified_list_store_products(woo: Any) -> list[dict[str, Any]]:
    return _load_unified_products(woo)


def _unified_update_store_price(woo: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    product_id = int(payload.get("product_id") or 0)
    if product_id <= 0:
        raise ValueError("Produto inválido.")
    product = woo.get_product(product_id)
    kind = _kind_for_product(product)
    if not kind:
        raise ValueError("O produto selecionado não pertence a Plugins, Temas ou Packs.")

    mode = str(payload.get("pricing_mode", "") or "").strip().lower()
    if kind == "pack" or mode == "direct" or str(product.get("type", "")).strip().lower() != "variable":
        regular, sale = pricing.normalize_price_pair(payload.get("regular_price"), payload.get("sale_price"))
        updated = woo.update_product_prices(product_id, regular, sale, authorized=True)
        _invalidate_cache()
        return {
            "ok": True,
            "message": f"Preços de {product.get('name') or ('#' + str(product_id))} atualizados.",
            "product": {
                "product_id": product_id,
                "product_name": str(updated.get("name") or product.get("name") or ""),
                "kind": kind,
                "pricing_mode": "direct",
                "regular_price": str(updated.get("regular_price", regular) or regular),
                "sale_price": str(updated.get("sale_price", sale) or sale),
                "last_price": str(updated.get("price") or sale or regular),
            },
        }

    variations = [
        row for row in woo.list_variations(
            product_id, per_page=100,
            _fields="id,name,sku,attributes,regular_price,sale_price",
        ) or [] if isinstance(row, Mapping)
    ]
    updates: list[dict[str, Any]] = []
    touched_periods: list[str] = []
    for period, label in (("annual", "anual"), ("lifetime", "vitalícia")):
        targets = [row for row in variations if pricing.variation_period(row) == period]
        if not targets:
            continue
        regular, sale = pricing.normalize_price_pair(
            payload.get(f"{period}_regular"), payload.get(f"{period}_sale")
        )
        updates.extend({"id": int(row["id"]), "regular_price": regular, "sale_price": sale} for row in targets)
        touched_periods.append(label)
    if not updates:
        raise ValueError("Nenhuma variação anual ou vitalícia foi encontrada neste produto.")
    updated = woo.update_variations_prices(product_id, updates, authorized=True)
    _invalidate_cache()
    return {
        "ok": True,
        "message": f"{len(updated)} variação(ões) de {product.get('name') or ('#' + str(product_id))} atualizadas ({', '.join(touched_periods)}).",
        "product_id": product_id,
        "updated_variation_count": len(updated),
    }


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-store-unified-pricing>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_store_management_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    pricing.list_store_pack_products = _unified_list_store_products
    pricing.update_store_pack_price = _unified_update_store_price
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
