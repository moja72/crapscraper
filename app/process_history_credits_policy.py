from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections.abc import Mapping
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import app.web as web
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "process_history_credits.js"
_CACHE_LOCK = threading.RLock()
_CACHE_TTL_SECONDS = 60.0
_CREDIT_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}

_PLUGINTHEME_PROBE_URL = "https://plugintheme.net/product/memberpress-downloads"
_PLUGINTHEME_ACCOUNT_URLS = (
    "https://plugintheme.net/pt-BR/account",
    "https://plugintheme.net/account",
)
_ULTRAPACK_BASE_URL = "https://www.ultrapackv2.com/"
_ULTRAPACK_ACCOUNT_URLS = (
    "https://www.ultrapackv2.com/minha-conta/",
    "https://www.ultrapackv2.com/minha-conta/downloads/",
    "https://www.ultrapackv2.com/my-account/",
    "https://www.ultrapackv2.com/",
)


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _as_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


_LIMIT_KEYS = {
    "downloadlimit", "downloadsperday", "dailydownloadlimit", "dailylimit",
    "maxdownloads", "maximumdownloads", "creditlimit", "maxcredits", "totalcredits",
}
_REMAINING_KEYS = {
    "remainingdownloads", "downloadsremaining", "dailydownloadsremaining",
    "remainingcredits", "creditsremaining", "availabledownloads", "availablecredits",
    "downloadbalance", "creditbalance", "remaining", "available", "balance",
}
_USED_KEYS = {
    "downloadsused", "useddownloads", "dailydownloadsused", "usedcredits",
    "creditsused", "downloadcount", "downloadscount", "used",
}


def _mapping_credit_numbers(value: Mapping[str, Any], context: str = "") -> dict[str, int] | None:
    context_key = _normalize_key(context)
    credit_context = any(term in context_key for term in ("download", "credit", "quota", "limit", "saldo"))
    found: dict[str, int] = {}

    for raw_key, raw_value in value.items():
        key = _normalize_key(raw_key)
        number = _as_nonnegative_int(raw_value)
        if number is None:
            continue
        if key in _LIMIT_KEYS or (credit_context and key in {"limit", "max", "total"}):
            found.setdefault("limit", number)
        elif key in _REMAINING_KEYS or (credit_context and key in {"remaining", "available", "balance"}):
            found.setdefault("remaining", number)
        elif key in _USED_KEYS or (credit_context and key in {"used", "count"}):
            found.setdefault("used", number)

    limit = found.get("limit")
    remaining = found.get("remaining")
    used = found.get("used")
    if limit is not None and remaining is None and used is not None:
        remaining = max(0, limit - used)
        found["remaining"] = remaining
    if limit is not None and remaining is not None:
        found["remaining"] = min(remaining, limit)
        if used is None:
            found["used"] = max(0, limit - found["remaining"])
        return found

    for raw_key, nested in value.items():
        nested_context = f"{context} {raw_key}".strip()
        result = _extract_credit_numbers(nested, context=nested_context)
        if result:
            return result
    return None


def _text_credit_numbers(value: str) -> dict[str, int] | None:
    text = unescape(str(value or ""))
    if not text.strip():
        return None

    # Primeiro tenta pares explicitamente associados a downloads/créditos.
    windows = re.findall(
        r"(?is).{0,90}(?:downloads?|cr[eé]ditos?|credits?|limite\s+di[aá]rio|daily\s+limit).{0,130}",
        text,
    )
    for window in windows:
        pair = re.search(r"(?i)(\d{1,5})\s*(?:/|de|of)\s*(\d{1,5})", window)
        if pair:
            first, limit = int(pair.group(1)), int(pair.group(2))
            if 0 <= first <= limit <= 100000:
                lower = window.lower()
                if re.search(r"used|usad[oa]s?|utilizad[oa]s?|consumid[oa]s?", lower):
                    remaining = max(0, limit - first)
                    return {"remaining": remaining, "limit": limit, "used": first}
                return {"remaining": first, "limit": limit, "used": max(0, limit - first)}

    # Depois tenta chaves JSON serializadas dentro de HTML/Next.js/RSC.
    key_patterns = {
        "limit": r'(?i)["\'](?:downloadLimit|dailyDownloadLimit|dailyLimit|maxDownloads|downloadsPerDay|creditLimit|maxCredits)["\']\s*:\s*["\']?(\d+)',
        "remaining": r'(?i)["\'](?:remainingDownloads|downloadsRemaining|dailyDownloadsRemaining|remainingCredits|creditsRemaining|availableDownloads|availableCredits|downloadBalance|creditBalance)["\']\s*:\s*["\']?(\d+)',
        "used": r'(?i)["\'](?:downloadsUsed|usedDownloads|dailyDownloadsUsed|usedCredits|creditsUsed|downloadCount)["\']\s*:\s*["\']?(\d+)',
    }
    found: dict[str, int] = {}
    for name, pattern in key_patterns.items():
        match = re.search(pattern, text)
        if match:
            found[name] = int(match.group(1))
    limit = found.get("limit")
    if limit is not None:
        if "remaining" not in found and "used" in found:
            found["remaining"] = max(0, limit - found["used"])
        if "remaining" in found:
            found["remaining"] = min(found["remaining"], limit)
            found.setdefault("used", max(0, limit - found["remaining"]))
            return found
    return None


def _extract_credit_numbers(value: Any, *, context: str = "") -> dict[str, int] | None:
    if isinstance(value, Mapping):
        return _mapping_credit_numbers(value, context=context)
    if isinstance(value, (list, tuple, set)):
        for item in value:
            result = _extract_credit_numbers(item, context=context)
            if result:
                return result
        return None
    return _text_credit_numbers(str(value or ""))


def _manager_from_handler(handler_class: type) -> Any:
    for method_name in ("_route_get", "_route_post", "do_GET"):
        method = getattr(handler_class, method_name, None)
        closure = getattr(method, "__closure__", None)
        freevars = getattr(getattr(method, "__code__", None), "co_freevars", ())
        if not closure:
            continue
        mapping = {name: cell.cell_contents for name, cell in zip(freevars, closure)}
        if "manager" in mapping:
            return mapping["manager"]
    return None


def _primary_app(manager: Any) -> Any:
    try:
        return web._get_primary_app(manager)
    except Exception:
        return None


def _session_for(app: Any, site_key: str, probe_url: str) -> Any:
    try:
        from app.integrations.ultrapack_session import (
            get_authenticated_plugintheme_session,
            get_authenticated_ultrapack_session,
        )
    except Exception as error:
        raise RuntimeError(f"Integração de sessão indisponível: {type(error).__name__}") from None

    factory = (
        get_authenticated_plugintheme_session
        if site_key == "plugintheme"
        else get_authenticated_ultrapack_session
    )
    auth = factory(app, probe_url)
    if hasattr(auth, "authenticated") and not bool(getattr(auth, "authenticated")):
        raise RuntimeError("Sessão não autenticada")
    session = getattr(auth, "session", None)
    if session is None:
        raise RuntimeError("Sessão HTTP autenticada indisponível")
    return session


def _from_response(response: Any) -> dict[str, int] | None:
    try:
        payload = response.json()
    except Exception:
        payload = None
    result = _extract_credit_numbers(payload) if payload is not None else None
    if result:
        return result
    return _extract_credit_numbers(getattr(response, "text", ""))


def _fetch_candidate_pages(session: Any, urls: tuple[str, ...]) -> tuple[dict[str, int] | None, str]:
    last_error = ""
    for url in urls:
        try:
            response = session.get(url, timeout=15, allow_redirects=True)
            if int(getattr(response, "status_code", 0) or 0) >= 400:
                last_error = f"HTTP {response.status_code}"
                continue
            result = _from_response(response)
            if result:
                return result, str(getattr(response, "url", "") or url)
        except Exception as error:
            last_error = type(error).__name__
    return None, last_error


def _plugintheme_credit(app: Any) -> dict[str, Any]:
    try:
        from app.integrations.plugintheme_download import PluginThemeDownloader

        session = _session_for(app, "plugintheme", _PLUGINTHEME_PROBE_URL)
        product_response = session.get(_PLUGINTHEME_PROBE_URL, timeout=15, allow_redirects=True)
        product_response.raise_for_status()
        product = PluginThemeDownloader.product_data(_PLUGINTHEME_PROBE_URL, product_response.text)
        product_id = str(product.get("id") or "").strip()
        if product_id:
            check = session.get(
                f"{PluginThemeDownloader.API_BASE}/downloads/{product_id}/check-access",
                timeout=15,
                allow_redirects=True,
            )
            check.raise_for_status()
            numbers = _from_response(check)
            if numbers:
                return {"ok": True, **numbers, "source": "check-access"}

        numbers, source = _fetch_candidate_pages(session, _PLUGINTHEME_ACCOUNT_URLS)
        if numbers:
            return {"ok": True, **numbers, "source": source}
        return {
            "ok": False,
            "message": "A sessão está disponível, mas o PluginTheme não expôs restante/limite de downloads nas respostas consultadas.",
        }
    except Exception as error:
        return {"ok": False, "message": f"PluginTheme: {sanitize_text(error)}"}


def _ultrapack_credit(app: Any) -> dict[str, Any]:
    try:
        session = _session_for(app, "ultrapackv2", urljoin(_ULTRAPACK_BASE_URL, "plugins/"))
        numbers, source = _fetch_candidate_pages(session, _ULTRAPACK_ACCOUNT_URLS)
        if numbers:
            return {"ok": True, **numbers, "source": source}
        return {
            "ok": False,
            "message": "A sessão está disponível, mas o UltraPackV2 não expôs restante/limite de downloads nas páginas consultadas.",
        }
    except Exception as error:
        return {"ok": False, "message": f"UltraPackV2: {sanitize_text(error)}"}


def _credit_snapshot(manager: Any) -> dict[str, Any]:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CREDIT_CACHE.get("payload")
        cached_at = float(_CREDIT_CACHE.get("at") or 0.0)
        if isinstance(cached, dict) and now - cached_at < _CACHE_TTL_SECONDS:
            return dict(cached)

    app = _primary_app(manager)
    if app is None:
        payload = {
            "ok": False,
            "ultrapackv2": {"ok": False, "message": "Aplicação principal indisponível."},
            "plugintheme": {"ok": False, "message": "Aplicação principal indisponível."},
        }
    else:
        ultrapack = _ultrapack_credit(app)
        plugintheme = _plugintheme_credit(app)
        payload = {
            "ok": bool(ultrapack.get("ok") or plugintheme.get("ok")),
            "ultrapackv2": ultrapack,
            "plugintheme": plugintheme,
        }

    with _CACHE_LOCK:
        _CREDIT_CACHE["at"] = now
        _CREDIT_CACHE["payload"] = dict(payload)
    return payload


def _script_block() -> str:
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-process-history-credits>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)

    class ProcessHistoryCreditsHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/processos/creditos":
                try:
                    self._send_json(_credit_snapshot(manager))
                except Exception as error:
                    self._send_json(
                        {"ok": False, "message": sanitize_text(error)},
                        code=500,
                    )
                return
            return super().do_GET()

    return _BASE_SERVER(server_address, ProcessHistoryCreditsHandler, *args, **kwargs)


def install_process_history_credits_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
