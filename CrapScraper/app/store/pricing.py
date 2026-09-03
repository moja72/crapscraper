from __future__ import annotations

import threading
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.store.woocommerce import is_pack, product_kind


def money(value, required=True):
    raw = str(value or "").replace("R$", "").strip().replace(",", ".")
    if not raw and not required:
        return ""
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("Preço inválido") from None
    if amount < 0:
        raise ValueError("Preço não pode ser negativo")
    return format(amount.quantize(Decimal("0.01")), "f")


def period(variation):
    text = " ".join(str(a.get("option") or "").lower() for a in variation.get("attributes", []) or []) + " " + str(variation.get("name") or "").lower()
    return "lifetime" if "vital" in text or "lifetime" in text else "annual" if "anual" in text or "annual" in text or "1 ano" in text or "12 meses" in text else ""


def confirmation_token(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(text.split())


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StorePricingService:
    def __init__(self, gateway, repository, write_enabled=False):
        self.gateway = gateway
        self.repository = repository
        self.write_enabled = write_enabled
        self._status_lock = threading.RLock()
        self._apply_lock = threading.Lock()
        self._status = {
            "state": "idle",
            "stage": "idle",
            "message": "Nenhuma aplicação de preços em andamento.",
            "progress": 0,
            "current": 0,
            "total": 0,
            "changed": 0,
            "unchanged": 0,
            "errors": [],
            "logs": [],
            "started_at": None,
            "finished_at": None,
        }

    def _selected(self, payload, products):
        kinds = set(payload.get("kinds") or [])
        product_ids = {int(x) for x in payload.get("product_ids", []) or []}
        return [
            product
            for product in products
            if product_kind(product) in kinds
            and not is_pack(product)
            and (not product_ids or int(product["id"]) in product_ids)
        ]

    def _set_status(self, **changes):
        with self._status_lock:
            self._status.update(changes)

    def _log(self, message):
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with self._status_lock:
            logs = list(self._status.get("logs") or [])
            logs.append(f"[{stamp}] {message}")
            self._status["logs"] = logs[-250:]

    def _begin(self, total):
        self._set_status(
            state="running",
            stage="validating",
            message=f"Validando preços de {total} produto(s).",
            progress=0,
            current=0,
            total=total,
            changed=0,
            unchanged=0,
            errors=[],
            logs=[],
            started_at=utc_now(),
            finished_at=None,
        )
        self._log("Aplicação iniciada. Validando produtos e variações antes de escrever no WooCommerce.")

    def status(self):
        with self._status_lock:
            return {
                "ok": True,
                **self._status,
                "logs": list(self._status.get("logs") or []),
                "errors": [dict(item) for item in self._status.get("errors") or []],
            }

    def _preview_selected(self, payload, selected, on_progress=None):
        changes = []
        prices = {
            f"{billing}_{kind}": money(payload.get(f"{billing}_{kind}"), kind == "regular")
            for billing in ("annual", "lifetime")
            for kind in ("regular", "sale")
        }
        total = len(selected)
        for index, product in enumerate(selected, 1):
            if on_progress:
                on_progress(index, total, product)
            for variation in self.gateway.variations(product["id"]):
                billing = period(variation)
                if not billing:
                    continue
                target_regular = prices[f"{billing}_regular"]
                target_sale = prices[f"{billing}_sale"]
                unchanged = str(variation.get("regular_price") or "") == target_regular and str(variation.get("sale_price") or "") == target_sale
                changes.append(
                    {
                        "product_id": int(product["id"]),
                        "product_name": product.get("name", ""),
                        "variation_id": int(variation["id"]),
                        "period": billing,
                        "current_regular": str(variation.get("regular_price") or ""),
                        "current_sale": str(variation.get("sale_price") or ""),
                        "regular_price": target_regular,
                        "sale_price": target_sale,
                        "status": "unchanged" if unchanged else "change",
                    }
                )
        return {
            "ok": True,
            "affected": sum(item["status"] == "change" for item in changes),
            "unchanged": sum(item["status"] == "unchanged" for item in changes),
            "changes": changes,
            "prices": prices,
            "kinds": sorted(set(payload.get("kinds") or [])),
        }

    def preview(self, payload, products):
        return self._preview_selected(payload, self._selected(payload, products))

    def apply(self, payload, products):
        if not self.write_enabled:
            raise PermissionError("Escrita da Loja desabilitada por SCRAPER_STORE_WRITE_ENABLED")
        if confirmation_token(payload.get("confirmation")) != "ALTERAR PRECOS":
            raise ValueError('Digite "ALTERAR PREÇOS" para confirmar')
        if not self._apply_lock.acquire(blocking=False):
            raise RuntimeError("Já existe uma aplicação de preços em andamento")

        selected = self._selected(payload, products)
        self._begin(len(selected))
        try:
            def validation_progress(index, total, product):
                progress = min(45, round((index / max(total, 1)) * 45))
                self._set_status(
                    stage="validating",
                    message=f"Validando preços: {index} de {total} produto(s).",
                    progress=progress,
                    current=index,
                    total=total,
                )
                if index == 1 or index == total or index % 25 == 0:
                    self._log(f"Validação {index}/{total}: {product.get('name', '')} · Woo #{product.get('id')}.")

            preview = self._preview_selected(payload, selected, validation_progress)
            self._set_status(unchanged=preview["unchanged"])
            self._log(f"Prévia concluída: {preview['affected']} preço(s) precisam de alteração e {preview['unchanged']} já estão corretos.")

            grouped = {}
            names = {}
            for row in preview["changes"]:
                if row["status"] != "change":
                    continue
                grouped.setdefault(row["product_id"], []).append(
                    {
                        "id": row["variation_id"],
                        "regular_price": row["regular_price"],
                        "sale_price": row["sale_price"],
                    }
                )
                names[row["product_id"]] = row["product_name"]

            changed = 0
            errors = []
            total_writes = len(grouped)
            self._set_status(
                stage="applying",
                message=f"Aplicando preços em {total_writes} produto(s)." if total_writes else "Nenhum preço precisa ser alterado.",
                progress=45 if total_writes else 100,
                current=0,
                total=total_writes,
            )

            for index, (product_id, updates) in enumerate(grouped.items(), 1):
                name = names.get(product_id, f"Woo #{product_id}")
                progress = 45 + round(((index - 1) / max(total_writes, 1)) * 55)
                self._set_status(
                    stage="applying",
                    message=f"Atualizando {index} de {total_writes}: {name}.",
                    progress=progress,
                    current=index,
                    total=total_writes,
                )
                self._log(f"Atualizando {index}/{total_writes}: {name} · Woo #{product_id} · {len(updates)} variação(ões).")
                try:
                    written = len(self.gateway.update_variations(product_id, updates))
                    changed += written
                    self._set_status(changed=changed)
                    self._log(f"OK: {name} · {written} preço(s) atualizado(s).")
                except Exception as exc:
                    error = {"product_id": product_id, "message": str(exc)}
                    errors.append(error)
                    self._set_status(errors=list(errors))
                    self._log(f"ERRO: {name} · Woo #{product_id} · {exc}")
                self._set_status(progress=45 + round((index / max(total_writes, 1)) * 55))

            result = {"ok": not errors, "changed": changed, "unchanged": preview["unchanged"], "errors": errors}
            self.repository.pricing_run("success" if not errors else "partial", payload, result)
            final_state = "success" if not errors else "partial"
            final_message = f"Concluído: {changed} preço(s) alterado(s); {preview['unchanged']} inalterado(s)."
            if errors:
                final_message += f" {len(errors)} produto(s) com erro."
            self._set_status(
                state=final_state,
                stage="completed",
                message=final_message,
                progress=100,
                changed=changed,
                unchanged=preview["unchanged"],
                errors=list(errors),
                finished_at=utc_now(),
            )
            self._log(final_message)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                stage="failed",
                message=f"Falha ao aplicar preços: {exc}",
                finished_at=utc_now(),
            )
            self._log(f"FALHA: {exc}")
            raise
        finally:
            self._apply_lock.release()
