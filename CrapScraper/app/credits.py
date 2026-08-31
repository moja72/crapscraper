from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
import weakref
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import requests

from app.updates.source_auth import (
    ensure_source_session,
    clear_source_session,
    get_source_account,
    get_source_diagnostic,
    get_source_session,
    set_source_state,
    source_state,
)


LOGGER = logging.getLogger("crapscraper.credits")
SUPPORTED_SITES = ("ultrapackv2", "plugintheme")
SITE_LABELS = {"ultrapackv2": "UltraPackV2", "plugintheme": "PluginTheme"}
ULTRAPACK_DASHBOARD_URL = "https://www.ultrapackv2.com/minha-conta/painel/"
PLUGINTHEME_PRODUCT_URL = "https://plugintheme.net/product/memberpress-downloads"
PLUGINTHEME_ACCESS_URL = "https://api.plugintheme.net/api/downloads/{download_id}/check-access"
PLUGINTHEME_ACCOUNT_ENDPOINTS = (
    ("https://api.plugintheme.net/api/users/me", "api:users/me"),
    ("https://api.plugintheme.net/api/membership/my", "api:membership/my"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


_LIMIT_KEYS = {
    "downloadlimit", "downloadsperday", "dailydownloadlimit", "dailylimit",
    "maxdownloads", "maximumdownloads", "creditlimit", "maxcredits", "totalcredits",
}
_REMAINING_KEYS = {
    "remainingdownloads", "downloadsremaining", "dailydownloadsremaining", "remainingcredits",
    "creditsremaining", "availabledownloads", "availablecredits", "downloadbalance",
    "creditbalance",
}
_USED_KEYS = {
    "downloadsused", "useddownloads", "dailydownloadsused", "usedcredits", "creditsused",
    "downloadcount", "downloadscount",
}


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
        result = extract_credit_numbers(nested, context=f"{context} {raw_key}".strip())
        if result:
            return result
    return found or None


def _extract_text(value: str) -> dict[str, int] | None:
    text = unescape(str(value or ""))
    windows = re.findall(
        r"(?is).{0,90}(?:downloads?|cr[eé]ditos?|credits?|limite\s+di[aá]rio|daily\s+limit).{0,130}",
        text,
    )
    for window in windows:
        pair = re.search(r"(?i)(\d{1,5})\s*(?:/|de|of)\s*(\d{1,5})", window)
        if pair:
            first, limit = int(pair.group(1)), int(pair.group(2))
            if 0 <= first <= limit <= 100000:
                if re.search(r"used|usad[oa]s?|utilizad[oa]s?|consumid[oa]s?", window.lower()):
                    return {"remaining": limit - first, "limit": limit, "used": first}
                return {"remaining": first, "limit": limit, "used": limit - first}
    patterns = {
        "limit": r"(?i)[\"'](?:downloadLimit|dailyDownloadLimit|dailyLimit|maxDownloads|downloadsPerDay|creditLimit|maxCredits)[\"']\s*:\s*[\"']?(\d+)",
        "remaining": r"(?i)[\"'](?:remainingDownloads|downloadsRemaining|dailyDownloadsRemaining|remainingCredits|creditsRemaining|availableDownloads|availableCredits|downloadBalance|creditBalance)[\"']\s*:\s*[\"']?(\d+)",
        "used": r"(?i)[\"'](?:downloadsUsed|usedDownloads|dailyDownloadsUsed|usedCredits|creditsUsed|downloadCount)[\"']\s*:\s*[\"']?(\d+)",
    }
    found = {name: int(match.group(1)) for name, pattern in patterns.items() if (match := re.search(pattern, text))}
    if "limit" in found and "remaining" not in found and "used" in found:
        found["remaining"] = max(0, found["limit"] - found["used"])
    if "limit" in found and "remaining" in found:
        found["remaining"] = min(found["remaining"], found["limit"])
        found.setdefault("used", max(0, found["limit"] - found["remaining"]))
        return found
    single = re.search(
        r"(?i)(?:saldo|restantes?|remaining|available)\D{0,24}(\d{1,6})\s*(?:downloads?|cr[eé]ditos?|credits?)?",
        text,
    )
    return {"remaining": int(single.group(1))} if single else None


def extract_credit_numbers(value: Any, *, context: str = "") -> dict[str, int] | None:
    if isinstance(value, Mapping):
        return _extract_mapping(value, context)
    if isinstance(value, (list, tuple, set)):
        for item in value:
            result = extract_credit_numbers(item, context=context)
            if result:
                return result
        return None
    return _extract_text(str(value or ""))


def _login_response(response: requests.Response) -> bool:
    final, sample = str(response.url or "").lower(), str(response.text or "")[:12000].lower()
    return any(marker in final for marker in ("/login", "/entrar", "wp-login")) or (
        'type="password"' in sample and any(marker in sample for marker in ("login", "entrar", "sign in"))
    )


def _response_numbers(response: requests.Response) -> dict[str, int] | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return extract_credit_numbers(payload) if payload is not None else extract_credit_numbers(response.text)


def _response_structure(response: requests.Response) -> str:
    """Return schema-only evidence; response values and credentials stay private."""
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type") or "unknown").split(";", 1)[0]
    try:
        payload = response.json()
    except ValueError:
        return f"Content-Type {content_type}; resposta não estruturada"
    paths: list[str] = []
    quota_paths: list[str] = []
    queue: list[tuple[str, Any, int]] = [("", payload, 0)]
    quota_marker = re.compile(r"(?i)(download|credit|quota|limit|remaining|used|balance|available)")
    while queue:
        prefix, value, depth = queue.pop(0)
        if isinstance(value, Mapping) and depth < 3:
            for raw_key, nested in value.items():
                key = re.sub(r"[^a-zA-Z0-9_-]+", "", str(raw_key))[:48]
                if not key:
                    continue
                path = f"{prefix}.{key}".strip(".")
                if len(paths) < 14 and depth <= 1:
                    paths.append(path)
                if quota_marker.search(key) and path not in quota_paths and len(quota_paths) < 10:
                    quota_paths.append(path)
                queue.append((path, nested, depth + 1))
        elif isinstance(value, (list, tuple)) and value and depth < 3:
            queue.append((f"{prefix}[]", value[0], depth + 1))
    structure = f"Content-Type {content_type}; chaves principais: {', '.join(paths) if paths else '(nenhuma)'}"
    if quota_paths:
        structure += f"; campos de quota: {', '.join(quota_paths)}"
    return structure


def _plugintheme_product_id(html: str) -> str:
    uuid = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    patterns = (
        rf"product\\?[\"']\s*:\s*\{{\s*\\?[\"']id\\?[\"']\s*:\s*\\?[\"']{uuid}",
        rf"\\?[\"']id\\?[\"']\s*:\s*\\?[\"']{uuid}",
    )
    for pattern in patterns:
        match = re.search(pattern, str(html or ""), re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _class_number(html: str, class_name: str) -> int | None:
    match = re.search(
        rf'<(?P<tag>[a-z0-9]+)[^>]*class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>(?P<body>.*?)</(?P=tag)>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    plain = re.sub(r"<[^>]+>", " ", unescape(match.group("body")))
    number = re.search(r"\b(\d{1,6})\b", plain)
    return int(number.group(1)) if number else None


def _session(site_key: str, account_key: str, product_url: str) -> requests.Session | None:
    existing = get_source_session(site_key, account_key)
    if isinstance(existing, requests.Session):
        diagnostic = get_source_diagnostic(site_key, account_key)
        if site_key != "plugintheme" or (
            source_state(site_key, account_key) == "validated" and diagnostic.get("authenticated") is True
        ):
            return existing
        clear_source_session(site_key, existing, account_key)
    created = ensure_source_session(
        site_key,
        product_url,
        account_key,
        allow_profile_probe=site_key == "plugintheme",
    )
    return created if isinstance(created, requests.Session) else None


def _failure(
    site_key: str,
    account_key: str,
    status: str,
    message: str,
    logs: list[str],
    *,
    authenticated: bool | None = None,
    limit: int | None = None,
    used: int | None = None,
    source: str = "",
) -> dict[str, Any]:
    if status in {"expired", "not_authenticated"}:
        authenticated = False
        set_source_state(site_key, "expired", account_key)
    elif authenticated is None:
        authenticated = source_state(site_key, account_key) == "validated"
    if site_key == "plugintheme" and authenticated and status in {"unavailable", "invalid", "credit_unavailable"}:
        message = "Autenticação confirmada, mas não foi possível localizar o saldo na página da conta."
        if limit is not None:
            message += f" Limite diário do plano: {limit}; o provedor não expôs o consumo/restante."
    payload = {
        "ok": False,
        "site_key": site_key,
        "account_key": account_key,
        "credits": None,
        "status": status,
        "message": message,
        "updated_at": _utc_now(),
        "logs": logs,
        "authenticated": bool(authenticated),
        "last_error": message,
        "limit": limit,
        "used": used,
        "source": source,
    }
    if site_key == "plugintheme":
        payload["session"] = get_source_diagnostic(site_key, account_key)
    return payload


def _provider_payload(site_key: str, account_key: str) -> dict[str, Any]:
    label = SITE_LABELS[site_key]
    logs = [f"Consultando créditos do {label}..."]
    product_url = ULTRAPACK_DASHBOARD_URL if site_key == "ultrapackv2" else PLUGINTHEME_PRODUCT_URL
    try:
        session = _session(site_key, account_key, product_url)
    except Exception as error:
        LOGGER.warning("Falha autenticando créditos %s/%s: %s", site_key, account_key, type(error).__name__)
        expired = any(term in str(error).lower() for term in ("login", "auth", "autent", "expir", "sess", "cookie"))
        return _failure(
            site_key,
            account_key,
            "expired" if expired else "unavailable",
            f"Não foi possível consultar os créditos porque a sessão do {label} expirou." if expired else f"Não foi possível confirmar a sessão do {label}.",
            logs + ["A sessão autenticada não pôde ser confirmada."],
        )
    if session is None:
        return _failure(
            site_key,
            account_key,
            "not_authenticated",
            f"Não foi possível consultar os créditos porque a sessão do {label} não está autenticada.",
            logs + ["Sessão autenticada indisponível."],
        )
    logs.extend(["Sessão autenticada confirmada.", "Consultando saldo..."])
    set_source_state(site_key, "validated", account_key)
    try:
        if site_key == "ultrapackv2":
            response = session.get(ULTRAPACK_DASHBOARD_URL, timeout=20, allow_redirects=True)
            if _login_response(response):
                return _failure(site_key, account_key, "expired", "Sessão expirada.", logs)
            if not response.ok:
                return _failure(site_key, account_key, f"http_{response.status_code}", "O painel de créditos não respondeu corretamente.", logs)
            limit = _class_number(response.text, "limite-diario-topline")
            used = _class_number(response.text, "baixados-hoje-topline")
            if limit is None or used is None:
                return _failure(site_key, account_key, "unavailable", "Saldo não encontrado no painel autenticado.", logs)
            if used > limit:
                return _failure(site_key, account_key, "invalid", "O painel retornou consumo maior que o limite diário.", logs)
            numbers = {"limit": limit, "used": used, "remaining": max(0, limit - used)}
            origin = "painel:.limite-diario-topline+.baixados-hoje-topline"
        else:
            numbers = None
            origin = ""
            observed_limit: int | None = None
            observed_used: int | None = None
            observed_source = ""
            for endpoint, endpoint_source in PLUGINTHEME_ACCOUNT_ENDPOINTS:
                account_response = session.get(endpoint, timeout=20, allow_redirects=True)
                logs.append(f"{endpoint_source} respondeu HTTP {account_response.status_code}.")
                logs.append(f"{endpoint_source}: {_response_structure(account_response)}.")
                if _login_response(account_response) or account_response.status_code == 401:
                    return _failure(site_key, account_key, "expired", "Sessão expirada.", logs)
                if account_response.ok:
                    candidate = _response_numbers(account_response)
                    if candidate and candidate.get("limit") is not None and observed_limit is None:
                        observed_limit = int(candidate["limit"])
                        observed_used = candidate.get("used")
                        observed_source = endpoint_source
                    if candidate and candidate.get("remaining") is not None:
                        numbers, origin = candidate, endpoint_source
                        logs.append(f"Saldo localizado na resposta estruturada {endpoint_source}.")
                        break
            if numbers is not None:
                credits = int(numbers["remaining"])
                updated_at = _utc_now()
                set_source_state(site_key, "validated", account_key)
                return {
                    "ok": True,
                    "site_key": site_key,
                    "account_key": account_key,
                    "credits": credits,
                    "remaining": credits,
                    "limit": numbers.get("limit"),
                    "used": numbers.get("used"),
                    "authenticated": True,
                    "status": "success",
                    "message": "Saldo consultado com sucesso.",
                    "source": origin,
                    "updated_at": updated_at,
                    "last_confirmed_at": updated_at,
                    "last_error": "",
                    "stale": False,
                    "logs": logs + [f"Saldo localizado: {credits}."],
                }
            response = session.get(PLUGINTHEME_PRODUCT_URL, timeout=20, allow_redirects=True)
            if _login_response(response):
                return _failure(site_key, account_key, "expired", "Sessão expirada.", logs)
            if not response.ok:
                return _failure(site_key, account_key, f"http_{response.status_code}", "A página autenticada não respondeu corretamente.", logs)
            product_id = _plugintheme_product_id(response.text)
            if not product_id:
                return _failure(site_key, account_key, "unavailable", "Identificador estruturado do download não encontrado.", logs, limit=observed_limit, used=observed_used, source=observed_source)
            access = session.get(PLUGINTHEME_ACCESS_URL.format(download_id=product_id), timeout=20, allow_redirects=True)
            logs.append(f"api:check-access respondeu HTTP {access.status_code}.")
            logs.append(f"api:check-access: {_response_structure(access)}.")
            if _login_response(access) or access.status_code == 401:
                return _failure(site_key, account_key, "expired", "Sessão expirada.", logs)
            if access.status_code == 403:
                return _failure(
                    site_key,
                    account_key,
                    "credit_unavailable",
                    "A sessão está autenticada, mas o endpoint não confirmou saldo para este produto.",
                    logs,
                    limit=observed_limit,
                    used=observed_used,
                    source=observed_source,
                )
            if not access.ok:
                return _failure(site_key, account_key, f"http_{access.status_code}", "O endpoint de saldo não respondeu corretamente.", logs)
            numbers = _response_numbers(access)
            if not numbers or numbers.get("remaining") is None:
                if numbers and numbers.get("limit") is not None and observed_limit is None:
                    observed_limit, observed_used, observed_source = int(numbers["limit"]), numbers.get("used"), "api:check-access"
                return _failure(site_key, account_key, "credit_unavailable", "Saldo não encontrado na resposta autenticada.", logs, limit=observed_limit, used=observed_used, source=observed_source)
            origin = "api:check-access"
        credits = int(numbers["remaining"])
        updated_at = _utc_now()
        return {
            "ok": True,
            "site_key": site_key,
            "account_key": account_key,
            "credits": credits,
            "remaining": credits,
            "limit": numbers.get("limit"),
            "used": numbers.get("used"),
            "authenticated": True,
            "status": "success",
            "message": "Saldo consultado com sucesso.",
            "source": origin,
            "updated_at": updated_at,
            "last_confirmed_at": updated_at,
            "last_error": "",
            "stale": False,
            "logs": logs + [f"Saldo localizado: {credits}."],
        }
    except requests.Timeout:
        LOGGER.warning("Timeout consultando créditos %s/%s", site_key, account_key)
        return _failure(site_key, account_key, "timeout", "Tempo limite ao consultar o serviço.", logs)
    except requests.RequestException as error:
        LOGGER.warning("Falha consultando créditos %s/%s: %s", site_key, account_key, type(error).__name__)
        return _failure(site_key, account_key, "unavailable", f"Serviço inacessível ({type(error).__name__}).", logs)


class CreditService:
    def __init__(
        self,
        data_dir: str | Path | None = None,
        provider: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._inflight: dict[tuple[str, str], threading.Event] = {}
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._provider = provider or _provider_payload
        self._path = Path(data_dir) / "source_credits.json" if data_dir else None
        self._load()
        _SERVICES.add(self)

    @staticmethod
    def _site(site_key: str) -> str:
        site = str(site_key or "").strip().lower()
        if site not in SUPPORTED_SITES:
            raise ValueError("Fonte de créditos inválida.")
        return site

    @staticmethod
    def _account(site_key: str, account_key: str) -> str:
        return str(account_key or get_source_account(site_key) or "default").strip().lower()

    @staticmethod
    def _storage_key(site_key: str, account_key: str) -> str:
        return f"{site_key}:{account_key}"

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            for storage_key, payload in raw.items():
                if not isinstance(payload, dict) or ":" not in storage_key:
                    continue
                site, account = storage_key.split(":", 1)
                if site in SUPPORTED_SITES and account:
                    self._cache[(site, account)] = dict(payload)
        except (OSError, ValueError):
            LOGGER.warning("Cache persistente de créditos inválido; uma nova consulta será necessária.")

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {self._storage_key(*key): value for key, value in self._cache.items()}
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def cached(self, site_key: str, account_key: str = "") -> dict[str, Any]:
        site, account = self._site(site_key), self._account(site_key, account_key)
        with self._lock:
            cached = self._cache.get((site, account))
            if cached:
                return dict(cached)
        return _failure(
            site,
            account,
            "unavailable",
            "Nenhum saldo confirmado para esta conta.",
            ["Use Atualizar créditos para fazer a primeira consulta."],
        )

    def invalidate(self, site_key: str, account_key: str = "") -> None:
        site, account = self._site(site_key), self._account(site_key, account_key)
        with self._lock:
            previous = self._cache.get((site, account))
            if previous:
                previous = dict(previous)
                previous["stale"] = True
                previous["message"] = "O saldo pode ter mudado após um download concluído."
                previous["logs"] = ["Saldo marcado como desatualizado após download concluído."]
                self._cache[(site, account)] = previous
                self._save()

    def refresh(self, site_key: str, account_key: str = "") -> dict[str, Any]:
        site, account = self._site(site_key), self._account(site_key, account_key)
        key = (site, account)
        with self._lock:
            event = self._inflight.get(key)
            owner = event is None
            if owner:
                event = threading.Event()
                self._inflight[key] = event
        assert event is not None
        if not owner:
            event.wait(timeout=45)
            return self.cached(site, account)
        try:
            candidate = dict(self._provider(site, account))
            candidate.setdefault("site_key", site)
            candidate.setdefault("account_key", account)
            candidate.setdefault("updated_at", _utc_now())
            with self._lock:
                previous = self._cache.get(key)
                if candidate.get("ok"):
                    candidate["stale"] = False
                    candidate["last_confirmed_at"] = candidate.get("last_confirmed_at") or candidate["updated_at"]
                    candidate["last_error"] = ""
                elif previous and previous.get("credits") is not None:
                    failure = candidate
                    candidate = dict(previous)
                    candidate.update({
                        "ok": False,
                        "status": failure.get("status", "unavailable"),
                        "message": failure.get("message", "Não foi possível atualizar os créditos."),
                        "logs": failure.get("logs", []),
                        "failed_at": failure.get("updated_at", _utc_now()),
                        "stale": True,
                        "authenticated": bool(failure.get("authenticated")),
                        "last_error": failure.get("message", "Não foi possível atualizar os créditos."),
                    })
                self._cache[key] = candidate
                self._save()
                return dict(candidate)
        finally:
            with self._lock:
                self._inflight.pop(key, None)
                event.set()

    def get(self, site_key: str, account_key: str = "", *, refresh: bool = False) -> dict[str, Any]:
        return self.refresh(site_key, account_key) if refresh else self.cached(site_key, account_key)

    def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        payload = {site: self.get(site, refresh=refresh) for site in SUPPORTED_SITES}
        payload["ok"] = any(bool(payload[site].get("ok")) for site in SUPPORTED_SITES)
        payload["cached"] = not refresh
        return payload


_SERVICES: weakref.WeakSet[CreditService] = weakref.WeakSet()


def invalidate_credit_cache(source_kind: str = "", account_key: str = "") -> None:
    sites = (str(source_kind or "").strip().lower(),) if source_kind else SUPPORTED_SITES
    for service in list(_SERVICES):
        for site in sites:
            if site in SUPPORTED_SITES:
                service.invalidate(site, account_key)


def refresh_credits_after_download(source_kind: str, account_key: str = "") -> None:
    site = str(source_kind or "").strip().lower()
    if site not in SUPPORTED_SITES:
        return
    for service in list(_SERVICES):
        service.invalidate(site, account_key)
        threading.Thread(
            target=service.refresh,
            args=(site, account_key),
            name=f"credits-refresh-{site}",
            daemon=True,
        ).start()
