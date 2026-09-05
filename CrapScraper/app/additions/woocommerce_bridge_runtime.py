from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

import requests


_ALLOWED = (
    re.compile(r"^/products$"),
    re.compile(r"^/products/\d+$"),
    re.compile(r"^/products/\d+/variations$"),
    re.compile(r"^/products/categories$"),
    re.compile(r"^/products/tags$"),
)


def _status(error: BaseException) -> int:
    if not isinstance(error, requests.HTTPError):
        return 0
    response = getattr(error, "response", None)
    return int(getattr(response, "status_code", 0) or 0)


def _allowed(method: str, path: str) -> bool:
    verb = str(method or "").upper()
    if verb not in {"GET", "POST", "PUT"}:
        return False
    return any(pattern.fullmatch(str(path or "")) for pattern in _ALLOWED)


def _site_base() -> str:
    value = str(os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").strip().rstrip("/")
    if "/wp-json/" in value:
        value = value.split("/wp-json/", 1)[0]
    return value


def install_addition_woocommerce_bridge() -> None:
    """Fallback HMAC para o namespace próprio quando o WAF bloqueia /wc/v3.

    O caminho normal continua sendo a API WooCommerce. Só 401/403 em operações
    estritamente permitidas são desviados para o bridge WordPress do CrapScraper.
    """

    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_store_bridge_installed", False):
        return

    original_wc = AdditionStoreGateway._wc

    def bridge_wc(self: Any, method: str, path: str, **kwargs: Any):
        if not _allowed(method, path):
            raise RuntimeError(f"Operação WooCommerce não permitida no bridge: {method} {path}")

        base = _site_base()
        secret = str(os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET") or "").strip()
        if not base:
            raise RuntimeError("WooCommerce REST foi bloqueado e SCRAPER_WP_BASE_URL não está configurado para o bridge CrapScraper.")
        if len(secret) < 24:
            raise RuntimeError(
                "WooCommerce REST foi bloqueado e SCRAPER_WORDPRESS_MANUAL_SECRET não está configurado para o bridge CrapScraper."
            )

        payload = {
            "method": str(method).upper(),
            "path": str(path),
            "params": dict(kwargs.get("params") or {}),
            "json": kwargs.get("json") if isinstance(kwargs.get("json"), dict) else {},
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"\n" + raw, hashlib.sha256).hexdigest()
        url = base + "/wp-json/crapscraper/v1/store-command"
        response = self.session.post(
            url,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-CrapScraper-Timestamp": timestamp,
                "X-CrapScraper-Signature": signature,
            },
            data=raw,
            timeout=max(int(getattr(self, "timeout", 60) or 60), 90),
        )
        if response.status_code == 404:
            raise RuntimeError(
                "WooCommerce REST está bloqueado pelo servidor e o bridge CrapScraper ainda não está instalado no WordPress."
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            detail = ""
            try:
                body = response.json()
                detail = str(body.get("message") or body.get("error") or "").strip()
            except Exception:
                detail = str(response.text or "").strip()[:300]
            raise RuntimeError(
                f"Bridge CrapScraper recusou {method} {path}: HTTP {response.status_code}"
                + (f" - {detail}" if detail else "")
            ) from error

        data = response.json()
        if not bool(data.get("ok")):
            raise RuntimeError(str(data.get("message") or data.get("error") or "Falha no bridge WooCommerce do CrapScraper."))
        return data.get("data")

    def wc(self: Any, method: str, path: str, **kwargs: Any):
        try:
            return original_wc(self, method, path, **kwargs)
        except requests.HTTPError as error:
            if _status(error) not in {401, 403} or not _allowed(method, path):
                raise
            return bridge_wc(self, method, path, **kwargs)

    AdditionStoreGateway._bridge_wc = bridge_wc
    AdditionStoreGateway._wc = wc
    AdditionStoreGateway._crapscraper_store_bridge_installed = True


__all__ = ["install_addition_woocommerce_bridge"]
