"""Escrita estritamente limitada e auditável de ``pt_versao``."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.request import Request

from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError, sanitize_text


def _fresh_product(woo: Any, product_id: int) -> Mapping[str, Any]:
    reader = getattr(woo, "get_product_fresh", None)
    return reader(product_id) if callable(reader) else woo.get_product(product_id)


def _single_meta(product: Mapping[str, Any]) -> tuple[int | None, str | None, str]:
    items = [item for item in product.get("meta_data", []) or []
             if isinstance(item, Mapping) and item.get("key") == "pt_versao"]
    if len(items) != 1:
        return None, None, "missing" if not items else "duplicate"
    item = items[0]
    try: meta_id = int(item["id"])
    except (KeyError, TypeError, ValueError): meta_id = None
    value = None if item.get("value") is None else str(item.get("value"))
    return meta_id, value, "present"


class VersionConfirmationError(IntegrationError):
    def __init__(self, message: str, evidence: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.evidence = dict(evidence)


def controlled_product_patch(woo: Any, product_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Executa PUT mínimo e devolve somente evidência segura, nunca o corpo arbitrário."""
    items = list(payload.get("meta_data") or [])
    if len(items) != 1 or set(items[0]) != {"id", "key", "value"} or items[0]["key"] != "pt_versao":
        raise IntegrationError("Payload de escrita WooCommerce fora do escopo pt_versao")
    url = woo.base_url.rstrip("/") + f"/wp-json/wc/v3/products/{int(product_id)}"
    request = Request(url, data=json.dumps(dict(payload)).encode("utf-8"), method="PUT",
                      headers={"Accept": "application/json", "Content-Type": "application/json",
                               "Authorization": woo._authorization(),
                               "User-Agent": "CrapScraper-controlled-update/1.0"})
    try:
        status, _headers, body = woo.transport(request, woo.timeout)
    except Exception as error:
        raise IntegrationError("Falha na escrita controlada: " +
                               sanitize_text(error, woo.username, woo.password)) from None
    evidence: dict[str, Any] = {
        "http_status": int(status), "response_body_present": bool(body),
        "product_id": None, "put_pt_versao": None, "put_meta_id": None,
        "confirmation_status": "http_error" if not 200 <= int(status) < 300 else "pending_get",
    }
    if not 200 <= int(status) < 300:
        raise VersionConfirmationError(f"WooCommerce recusou atualização controlada: HTTP {status}", evidence)
    if not body:
        evidence["confirmation_status"] = "put_body_absent"
        return evidence
    try:
        response = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        evidence["confirmation_status"] = "put_json_invalid"
        raise VersionConfirmationError("WooCommerce retornou JSON inválido no PUT", evidence) from None
    if not isinstance(response, Mapping):
        evidence["confirmation_status"] = "put_json_invalid"
        raise VersionConfirmationError("WooCommerce retornou estrutura inválida no PUT", evidence)
    evidence["product_id"] = response.get("id")
    meta_id, value, status_name = _single_meta(response)
    evidence.update(put_meta_id=meta_id, put_pt_versao=value,
                    confirmation_status="pending_get" if status_name == "present" else f"put_meta_{status_name}")
    return evidence


@dataclass(frozen=True)
class VersionChangePlan:
    product_id: int
    meta_id: int
    previous_value: str
    target_value: str

    def payload(self, value: str | None = None) -> dict[str, Any]:
        return {"meta_data": [{"id": self.meta_id, "key": "pt_versao",
                               "value": self.target_value if value is None else value}]}

    def rollback_payload(self) -> dict[str, Any]:
        return self.payload(self.previous_value)


class WooCommerceVersionWriter:
    def __init__(self, woo: Any, *, write_enabled: bool = False,
                 patch: Callable[[int, Mapping[str, Any]], Any] | None = None) -> None:
        self.woo, self.write_enabled, self.patch = woo, bool(write_enabled), patch

    def prepare(self, product_id: int, expected_value: str, target_value: str) -> VersionChangePlan:
        product = _fresh_product(self.woo, product_id)
        if int(product.get("id") or 0) != int(product_id):
            raise IntegrationError("WooCommerce retornou produto diferente antes da escrita")
        meta_id, value, status_name = _single_meta(product)
        if status_name != "present" or meta_id is None:
            raise IntegrationError("pt_versao existente e seu meta ID devem ser únicos")
        if value != expected_value:
            raise IntegrationError("pt_versao divergiu imediatamente antes da escrita")
        return VersionChangePlan(product_id, meta_id, expected_value, target_value)

    def _ensure_enabled(self) -> None:
        if not self.write_enabled:
            raise WriteOperationDisabledError("WORDPRESS_WRITE_ENABLED=False")
        if self.patch is None:
            raise IntegrationError("Transporte de escrita WooCommerce não configurado")

    def apply_and_confirm(self, plan: VersionChangePlan, *, rollback: bool = False) -> dict[str, Any]:
        self._ensure_enabled()
        expected = plan.previous_value if rollback else plan.target_value
        payload = plan.rollback_payload() if rollback else plan.payload()
        raw = self.patch(plan.product_id, payload)
        evidence = dict(raw) if isinstance(raw, Mapping) else {
            "http_status": None, "response_body_present": None, "product_id": None,
            "put_pt_versao": None, "put_meta_id": None, "confirmation_status": "legacy_patch",
        }
        put_value = evidence.get("put_pt_versao")
        put_meta_id = evidence.get("put_meta_id")
        body_present = evidence.get("response_body_present")
        product = _fresh_product(self.woo, plan.product_id)
        get_meta_id, get_value, get_status = _single_meta(product)
        evidence.update(get_product_id=product.get("id"), get_pt_versao=get_value,
                        get_meta_id=get_meta_id, get_cache_busted=True)
        put_ok = evidence.get("confirmation_status") == "legacy_patch" or body_present is False or (
            put_value == expected and put_meta_id == plan.meta_id
            and int(evidence.get("product_id") or 0) == plan.product_id
        )
        get_ok = (get_status == "present" and get_meta_id == plan.meta_id
                  and get_value == expected and int(product.get("id") or 0) == plan.product_id)
        evidence["confirmation_status"] = "confirmed" if put_ok and get_ok else "diverged"
        if not put_ok or not get_ok:
            raise VersionConfirmationError("WooCommerce não confirmou pt_versao", evidence)
        return evidence

    def apply(self, plan: VersionChangePlan) -> dict[str, Any]:
        return self.apply_and_confirm(plan)

    def rollback(self, plan: VersionChangePlan) -> dict[str, Any]:
        return self.apply_and_confirm(plan, rollback=True)
