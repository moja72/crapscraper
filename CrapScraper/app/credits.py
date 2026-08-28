from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from collections.abc import Mapping
from html import unescape
from typing import Any

import requests

from app.updates.source_auth import get_source_session, source_state


LOGGER = logging.getLogger("crapscraper.credits")
_CACHE_LOCK = threading.RLock()
_CACHE_TTL_SECONDS = 60.0
_CACHE: dict[str, Any] = {"at": 0.0, "session_ids": (), "payload": None}

_PLUGINTHEME_PRODUCT_URL = "https://plugintheme.net/product/memberpress-downloads"
_PLUGINTHEME_ACCOUNT_URLS = (
    "https://plugintheme.net/pt-BR/account",
    "https://plugintheme.net/account",
)
_ULTRAPACK_ACCOUNT_URLS = (
    "https://www.ultrapackv2.com/minha-conta/",
    "https://www.ultrapackv2.com/minha-conta/downloads/",
    "https://www.ultrapackv2.com/my-account/",
    "https://www.ultrapackv2.com/",
)


def invalidate_credit_cache(_source_kind: str = "") -> None:
    with _CACHE_LOCK:
        _CACHE.update({"at": 0.0, "session_ids": (), "payload": None})


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


_LIMIT_KEYS = {"downloadlimit", "downloadsperday", "dailydownloadlimit", "dailylimit", "maxdownloads", "maximumdownloads", "creditlimit", "maxcredits", "totalcredits"}
_REMAINING_KEYS = {"remainingdownloads", "downloadsremaining", "dailydownloadsremaining", "remainingcredits", "creditsremaining", "availabledownloads", "availablecredits", "downloadbalance", "creditbalance", "remaining", "available", "balance"}
_USED_KEYS = {"downloadsused", "useddownloads", "dailydownloadsused", "usedcredits", "creditsused", "downloadcount", "downloadscount", "used"}


def _extract_mapping(value: Mapping[str, Any], context: str = "") -> dict[str, int] | None:
    context_key = _normalize_key(context)
    credit_context = any(term in context_key for term in ("download", "credit", "quota", "limit", "saldo"))
    found: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key, number = _normalize_key(raw_key), _nonnegative_int(raw_value)
        if number is None:
            continue
        if key in _LIMIT_KEYS or (credit_context and key in {"limit", "max", "total"}):
            found.setdefault("limit", number)
        elif key in _REMAINING_KEYS or (credit_context and key in {"remaining", "available", "balance"}):
            found.setdefault("remaining", number)
        elif key in _USED_KEYS or (credit_context and key in {"used", "count"}):
            found.setdefault("used", number)
    limit, remaining, used = found.get("limit"), found.get("remaining"), found.get("used")
    if limit is not None and remaining is None and used is not None:
        found["remaining"] = remaining = max(0, limit - used)
    if limit is not None and remaining is not None:
        found["remaining"] = min(remaining, limit)
        found.setdefault("used", max(0, limit - found["remaining"]))
        return found
    if remaining is not None:
        return found
    for raw_key, nested in value.items():
        if result := extract_credit_numbers(nested, context=f"{context} {raw_key}".strip()):
            return result
    return None


def _extract_text(value: str) -> dict[str, int] | None:
    text = unescape(str(value or ""))
    windows = re.findall(r"(?is).{0,90}(?:downloads?|cr[eé]ditos?|credits?|limite\s+di[aá]rio|daily\s+limit).{0,130}", text)
    for window in windows:
        pair = re.search(r"(?i)(\d{1,5})\s*(?:/|de|of)\s*(\d{1,5})", window)
        if pair:
            first, limit = int(pair.group(1)), int(pair.group(2))
            if 0 <= first <= limit <= 100000:
                if re.search(r"used|usad[oa]s?|utilizad[oa]s?|consumid[oa]s?", window.lower()):
                    return {"remaining": limit - first, "limit": limit, "used": first}
                return {"remaining": first, "limit": limit, "used": limit - first}
    patterns = {
        "limit": r'(?i)["\'](?:downloadLimit|dailyDownloadLimit|dailyLimit|maxDownloads|downloadsPerDay|creditLimit|maxCredits)["\']\s*:\s*["\']?(\d+)',
        "remaining": r'(?i)["\'](?:remainingDownloads|downloadsRemaining|dailyDownloadsRemaining|remainingCredits|creditsRemaining|availableDownloads|availableCredits|downloadBalance|creditBalance)["\']\s*:\s*["\']?(\d+)',
        "used": r'(?i)["\'](?:downloadsUsed|usedDownloads|dailyDownloadsUsed|usedCredits|creditsUsed|downloadCount)["\']\s*:\s*["\']?(\d+)',
    }
    found = {name: int(match.group(1)) for name, pattern in patterns.items() if (match := re.search(pattern, text))}
    if "limit" in found and "remaining" not in found and "used" in found:
        found["remaining"] = max(0, found["limit"] - found["used"])
    if "limit" in found and "remaining" in found:
        found["remaining"] = min(found["remaining"], found["limit"])
        found.setdefault("used", max(0, found["limit"] - found["remaining"]))
        return found
    single = re.search(r"(?i)(?:saldo|restantes?|remaining|available)\D{0,24}(\d{1,6})\s*(?:downloads?|cr[eé]ditos?|credits?)?", text)
    if single:
        return {"remaining": int(single.group(1))}
    return None


def extract_credit_numbers(value: Any, *, context: str = "") -> dict[str, int] | None:
    if isinstance(value, Mapping):
        return _extract_mapping(value, context)
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if result := extract_credit_numbers(item, context=context):
                return result
        return None
    return _extract_text(str(value or ""))


def _env_json(name: str) -> dict[str, str]:
    try:
        value = json.loads(os.getenv(name, "{}") or "{}")
    except json.JSONDecodeError:
        return {}
    return {str(key): str(item) for key, item in value.items()} if isinstance(value, dict) else {}


def _session(source_kind: str) -> tuple[requests.Session | None, bool]:
    shared = get_source_session(source_kind)
    if isinstance(shared, requests.Session):
        return shared, False
    prefix = "SCRAPER_ULTRAPACK" if source_kind == "ultrapackv2" else "SCRAPER_PLUGINTHEME"
    headers, cookies = _env_json(prefix + "_HEADERS_JSON"), _env_json(prefix + "_COOKIES_JSON")
    if not headers and not cookies:
        return None, False
    created = requests.Session()
    created.headers.update(headers)
    created.cookies.update(cookies)
    return created, True


def _login_response(response: requests.Response) -> bool:
    final, sample = str(response.url or "").lower(), str(response.text or "")[:12000].lower()
    return any(marker in final for marker in ("/login", "/entrar", "wp-login")) or ("type=\"password\"" in sample and any(marker in sample for marker in ("login", "entrar", "sign in")))


def _response_numbers(response: requests.Response) -> dict[str, int] | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return extract_credit_numbers(payload) if payload is not None else extract_credit_numbers(response.text)


def _probe_pages(session: requests.Session, urls: tuple[str, ...]) -> tuple[dict[str, int] | None, str]:
    last = "element_not_found"
    for url in urls:
        try:
            response = session.get(url, timeout=15, allow_redirects=True)
            if _login_response(response):
                return None, "session_expired"
            if response.status_code >= 400:
                last = f"http_{response.status_code}"
                continue
            if numbers := _response_numbers(response):
                return numbers, str(response.url or url)
        except requests.Timeout:
            last = "timeout"
        except requests.RequestException as error:
            last = type(error).__name__
    return None, last


def _provider_payload(source_kind: str) -> dict[str, Any]:
    session, owned = _session(source_kind)
    label = "UltraPackV2" if source_kind == "ultrapackv2" else "PluginTheme"
    if session is None:
        return {"ok": False, "status": "not_authenticated", "message": "Sessão não autenticada."}
    try:
        if source_kind == "plugintheme":
            response = session.get(_PLUGINTHEME_PRODUCT_URL, timeout=15, allow_redirects=True)
            if _login_response(response):
                return {"ok": False, "status": "expired", "message": "Sessão expirada."}
            if response.ok:
                match = re.search(r'"id"\s*:\s*"([0-9a-f-]{20,})"', response.text, re.I)
                if match:
                    check = session.get(f"https://api.plugintheme.net/api/downloads/{match.group(1)}/check-access", timeout=15, allow_redirects=True)
                    if check.ok and (numbers := _response_numbers(check)):
                        return {"ok": True, **numbers, "status": "available", "source": "check-access"}
            numbers, source = _probe_pages(session, _PLUGINTHEME_ACCOUNT_URLS)
        else:
            numbers, source = _probe_pages(session, _ULTRAPACK_ACCOUNT_URLS)
        if numbers:
            return {"ok": True, **numbers, "status": "available", "source": source}
        status = "expired" if source == "session_expired" else "unavailable"
        LOGGER.warning("Créditos %s indisponíveis: %s; estado_auth=%s", label, source, source_state(source_kind))
        return {"ok": False, "status": status, "message": "Sessão expirada." if status == "expired" else "Saldo não encontrado na resposta autenticada."}
    except requests.Timeout:
        LOGGER.warning("Timeout consultando créditos %s", label)
        return {"ok": False, "status": "timeout", "message": "Tempo limite ao consultar o serviço."}
    except requests.RequestException as error:
        LOGGER.warning("Falha consultando créditos %s: %s", label, type(error).__name__)
        return {"ok": False, "status": "unavailable", "message": f"Serviço inacessível ({type(error).__name__})."}
    finally:
        if owned:
            session.close()


class CreditService:
    def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        session_ids = tuple(id(get_source_session(key)) for key in ("ultrapackv2", "plugintheme"))
        with _CACHE_LOCK:
            cached = _CACHE.get("payload")
            fresh = now - float(_CACHE.get("at") or 0.0) < _CACHE_TTL_SECONDS
            if not refresh and fresh and _CACHE.get("session_ids") == session_ids and isinstance(cached, dict):
                return dict(cached)
        ultrapack, plugintheme = _provider_payload("ultrapackv2"), _provider_payload("plugintheme")
        payload = {"ok": bool(ultrapack.get("ok") or plugintheme.get("ok")), "ultrapackv2": ultrapack, "plugintheme": plugintheme, "cached": False}
        with _CACHE_LOCK:
            _CACHE.update({"at": now, "session_ids": session_ids, "payload": payload})
        return payload
