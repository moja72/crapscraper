from __future__ import annotations

import time
from typing import Any

from app.updates.adapters import WooCommerceGateway, normalize_version


_ORIGINAL_SET_VERSION = WooCommerceGateway.set_version
_ORIGINAL_CONFIRM_VERSION = WooCommerceGateway.confirm_version


def _authoritative_put(evidence: dict[str, Any], product_id: int, version: str) -> bool:
    requested = normalize_version(version)
    put = evidence.get("put") or {}
    return bool(
        evidence.get("confirmation_status") == "put_confirmed"
        and int(evidence.get("http_status") or 0) in {200, 201}
        and int(evidence.get("product_id") or 0) == int(product_id)
        and int(put.get("product_id") or 0) == int(product_id)
        and str(put.get("status") or "") == "single"
        and normalize_version(put.get("value")) == requested
        and int(put.get("count") or 0) == 1
    )


def _set_version(self: WooCommerceGateway, product_id: int, version: str) -> dict[str, Any]:
    evidence = dict(_ORIGINAL_SET_VERSION(self, product_id, version) or {})
    if _authoritative_put(evidence, product_id, version):
        self._crapscraper_authoritative_put = {
            "product_id": int(product_id),
            "version": normalize_version(version),
            "at": time.monotonic(),
            "evidence": evidence,
        }
    else:
        self._crapscraper_authoritative_put = None
    return evidence


def _confirm_version(self: WooCommerceGateway, product_id: int, version: str) -> dict[str, Any]:
    cached = getattr(self, "_crapscraper_authoritative_put", None)
    expected = normalize_version(version)
    if isinstance(cached, dict):
        age = time.monotonic() - float(cached.get("at") or 0.0)
        if (
            age <= 10.0
            and int(cached.get("product_id") or 0) == int(product_id)
            and normalize_version(cached.get("version")) == expected
        ):
            self._crapscraper_authoritative_put = None
            write = dict(cached.get("evidence") or {})
            put = write.get("put") or {}
            return {
                "method": "PUT",
                "endpoint": f"/products/{int(product_id)}",
                "product_id": int(product_id),
                "requested_pt_versao": expected,
                "expected_pt_versao": expected,
                "observed_pt_versao": normalize_version(put.get("value")),
                "gets": [],
                "put": put,
                "http_status": write.get("http_status"),
                "confirmation_status": "confirmed_by_put_response",
                "diagnosis": "Resposta HTTP do PUT confirmou produto, meta única e valor solicitado; leitura GET redundante foi dispensada.",
            }
    self._crapscraper_authoritative_put = None
    return _ORIGINAL_CONFIRM_VERSION(self, product_id, version)


def install_fast_transaction() -> None:
    if getattr(WooCommerceGateway, "_crapscraper_fast_transaction_installed", False):
        return
    WooCommerceGateway.set_version = _set_version
    WooCommerceGateway.confirm_version = _confirm_version
    WooCommerceGateway._crapscraper_fast_transaction_installed = True


install_fast_transaction()

__all__ = ["install_fast_transaction", "_authoritative_put"]
