from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


_ALLOWED = (
    re.compile(r"^/products$"),
    re.compile(r"^/products/\d+$"),
    re.compile(r"^/products/\d+/variations$"),
    re.compile(r"^/products/\d+/variations/\d+$"),
    re.compile(r"^/products/categories$"),
    re.compile(r"^/products/tags$"),
    re.compile(r"^/media$"),
)


def _status(error: BaseException) -> int:
    if not isinstance(error, requests.HTTPError):
        return 0
    response = getattr(error, "response", None)
    return int(getattr(response, "status_code", 0) or 0)


def _transport_failure(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
    )


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


def _bridge_error(response: requests.Response, method: str, path: str) -> RuntimeError:
    detail = ""
    version = ""
    try:
        body = response.json()
        detail = str(body.get("message") or body.get("error") or "").strip()
        version = str(body.get("bridge_version") or (body.get("data") or {}).get("bridge_version") or "").strip()
    except Exception:
        detail = str(response.text or "").strip()[:300]
    suffix = f" [bridge {version}]" if version else ""
    return RuntimeError(
        f"Bridge CrapScraper recusou {method} {path}: HTTP {response.status_code}{suffix}"
        + (f" - {detail}" if detail else "")
    )


def install_addition_woocommerce_bridge() -> None:
    """Fallback HMAC para namespace próprio quando REST/WAF não é confiável."""

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

        command = {
            "method": str(method).upper(),
            "path": str(path),
            "params": dict(kwargs.get("params") or {}),
            "json": kwargs.get("json") if isinstance(kwargs.get("json"), dict) else {},
        }
        command_raw = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoded = base64.b64encode(command_raw).decode("ascii")
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"),
            timestamp.encode("ascii") + b"\n" + encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        envelope = {"t": timestamp, "s": signature, "p": encoded}
        url = base + "/wp-json/crapscraper/v2/bridge"
        try:
            response = self.session.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
                },
                json=envelope,
                timeout=max(int(getattr(self, "timeout", 60) or 60), 120),
            )
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            raise RuntimeError(
                f"Bridge CrapScraper não conseguiu conectar a {url}: {type(error).__name__}: {error}"
            ) from error
        if response.status_code == 404:
            raise RuntimeError(
                "WooCommerce REST está bloqueado pelo servidor e o bridge CrapScraper V2 ainda não está instalado no WordPress."
            )
        if response.status_code >= 400:
            raise _bridge_error(response, method, path)

        try:
            data = response.json()
        except Exception as error:
            raise RuntimeError("Bridge CrapScraper retornou resposta inválida em vez de JSON.") from error
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
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if not _allowed(method, path):
                raise
            return bridge_wc(self, method, path, **kwargs)

    def upload_media_bridge(self: Any, path: Path, title: str) -> int:
        file = Path(path)
        raw = file.read_bytes()
        if len(raw) <= 1024:
            raise RuntimeError("Imagem validada está vazia ou pequena demais antes do bridge.")
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        payload = {
            "filename": file.name,
            "title": str(title or file.stem),
            "mime": mime,
            "content_b64": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        media = bridge_wc(self, "POST", "/media", json=payload)
        media_id = int((media or {}).get("id") or 0) if isinstance(media, dict) else 0
        if not media_id:
            raise RuntimeError("Bridge CrapScraper não retornou o ID da mídia criada.")
        return media_id

    AdditionStoreGateway._bridge_wc = bridge_wc
    AdditionStoreGateway._wc = wc
    AdditionStoreGateway.upload_media_bridge = upload_media_bridge
    AdditionStoreGateway._crapscraper_store_bridge_installed = True


__all__ = ["install_addition_woocommerce_bridge"]
