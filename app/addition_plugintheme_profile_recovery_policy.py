from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import Any, Callable, Mapping

from app import settings
import app.addition_one_click_policy as one_click
import app.addition_retry_recovery_policy as retry
import app.new_product_workflow_policy as additions
import app.web as web


_INSTALLED = False
_BASE_DOWNLOAD_SOURCE: Callable[..., dict[str, Any]] | None = None

_DIRECT_TIMEOUT_SECONDS = 90
_DIRECT_RETRIES = 3
_DIRECT_RETRY_DELAY_SECONDS = 1.0
_TRANSIENT_MARKERS = (
    "timed out",
    "timeout",
    "urlopen error",
    "temporarily unavailable",
    "temporary failure",
    "connection reset",
    "connection aborted",
    "remote end closed",
    "read timed out",
    "read timeout",
    "502",
    "503",
    "504",
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_transient_error(error: BaseException) -> bool:
    text = _clean(error).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _account_key(primary: Any) -> str:
    context = getattr(primary, "context", None)
    if isinstance(context, Mapping):
        value = context.get("account_key")
    else:
        value = getattr(context, "account_key", "")
    return _clean(value) or _clean(getattr(settings, "DEFAULT_ACCOUNT_KEY", "")) or "default"


def _find_access_token(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("access_token", "accessToken", "token", "jwt"):
            token = _clean(value.get(key))
            if len(token) >= 40:
                return token
        for nested in value.values():
            token = _find_access_token(nested)
            if token:
                return token
    elif isinstance(value, (list, tuple)):
        for nested in value:
            token = _find_access_token(nested)
            if token:
                return token
    elif isinstance(value, str):
        raw = value.strip()
        if raw.startswith("{") or raw.startswith("["):
            with suppress(Exception):
                return _find_access_token(json.loads(raw))
    return ""


def _profile_http_session(primary: Any) -> tuple[Any | None, str]:
    """Lê cookies/tokens do perfil exclusivo criado pelo botão Renovar sessão."""
    try:
        import requests
        from playwright.sync_api import sync_playwright
        from app.browser import get_plugintheme_profile_dir
    except Exception as error:
        return None, f"Dependência de recuperação indisponível: {type(error).__name__}."

    profile_dir = get_plugintheme_profile_dir(_account_key(primary))
    if not profile_dir.exists():
        return None, f"Perfil PluginTheme ainda não existe em {profile_dir}."

    cookies: list[dict[str, Any]] = []
    storage_rows: list[dict[str, Any]] = []
    last_error: BaseException | None = None

    try:
        with sync_playwright() as playwright:
            context = None
            launch_variants = (
                {"channel": "chrome", "headless": True},
                {"headless": True},
            )
            for kwargs in launch_variants:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        args=["--disable-blink-features=AutomationControlled"],
                        **kwargs,
                    )
                    break
                except Exception as error:
                    last_error = error
            if context is None:
                detail = _clean(last_error)
                if "profile" in detail.lower() or "singleton" in detail.lower() or "in use" in detail.lower():
                    return None, (
                        "O perfil PluginTheme ainda está aberto/em uso. Feche completamente a janela Chrome aberta por "
                        "Renovar sessão e tente novamente."
                    )
                return None, f"Não foi possível abrir o perfil PluginTheme para reler os cookies: {type(last_error).__name__}."

            try:
                cookies = list(context.cookies(["https://plugintheme.net", "https://api.plugintheme.net"]) or [])
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto("https://plugintheme.net/pt-BR/account", wait_until="domcontentloaded", timeout=45_000)
                except Exception:
                    pass
                with suppress(Exception):
                    storage_rows = list(
                        page.evaluate(
                            """() => Object.keys(localStorage).map(key => ({key, value: localStorage.getItem(key) || ''}))"""
                        )
                        or []
                    )
            finally:
                context.close()
    except Exception as error:
        return None, f"Falha ao reler o perfil PluginTheme: {type(error).__name__}."

    if not cookies and not storage_rows:
        return None, "O perfil foi aberto, mas nenhum cookie/token autenticado do PluginTheme foi encontrado."

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": str(getattr(settings, "PLAYWRIGHT_USER_AGENT", "Mozilla/5.0")),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": str(getattr(settings, "HTTP_ACCEPT_LANGUAGE", "pt-BR,pt;q=0.9,en-US;q=0.8")),
            "Origin": "https://plugintheme.net",
            "Referer": "https://plugintheme.net/",
        }
    )
    for cookie in cookies:
        name = _clean(cookie.get("name"))
        value = str(cookie.get("value") or "")
        if not name or not value:
            continue
        domain = _clean(cookie.get("domain")) or ".plugintheme.net"
        path = _clean(cookie.get("path")) or "/"
        with suppress(Exception):
            session.cookies.set(name, value, domain=domain, path=path)

    token = ""
    for row in storage_rows:
        if not isinstance(row, Mapping):
            continue
        token = _find_access_token(row.get("value"))
        if token:
            break
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    return session, (
        f"Perfil renovado relido diretamente: {len(cookies)} cookie(s)"
        + (" e token de acesso encontrado." if token else ".")
    )


def _direct_download_resilient(job_id: str, session: Any) -> dict[str, Any]:
    from app.integrations.plugintheme_download import PluginThemeDownloader

    job = additions._row(job_id)
    source_url = _clean(job.get("source_product_url"))
    staging_dir = additions._STAGING_ROOT / additions._safe_job_id(job_id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    downloader = PluginThemeDownloader(
        session,
        timeout=_DIRECT_TIMEOUT_SECONDS,
        retries=_DIRECT_RETRIES,
        retry_delay=_DIRECT_RETRY_DELAY_SECONDS,
    )
    artifact, detected_version = downloader.download(source_url, staging_dir)
    one_click._emit(
        job_id,
        (
            "ZIP recuperado pela sessão HTTP direta do PluginTheme com timeout estendido "
            f"({_DIRECT_TIMEOUT_SECONDS}s) e retry de rede."
        ),
        step="zip",
        progress=83,
    )
    return retry._persist_download(job_id, artifact, detected_version)


def _download_source_with_profile_recovery(job_id: str, manager: Any) -> dict[str, Any]:
    if _BASE_DOWNLOAD_SOURCE is None:
        raise RuntimeError("Downloader PluginTheme base indisponível.")

    job = additions._row(job_id)
    source_url = _clean(job.get("source_product_url"))
    if "plugintheme.net" not in source_url.lower():
        return _BASE_DOWNLOAD_SOURCE(job_id, manager)

    try:
        return _BASE_DOWNLOAD_SOURCE(job_id, manager)
    except Exception as first_error:
        if retry._is_credit_error(first_error):
            raise
        is_session = retry._is_plugintheme_session_error(first_error)
        is_transient = _is_transient_error(first_error)
        if not is_session and not is_transient:
            raise

        primary = web._get_primary_app(manager) if manager is not None else None

        if is_transient:
            one_click._emit(
                job_id,
                "Timeout/falha transitória detectada no PluginTheme. Reaproveitando a sessão e repetindo o ZIP com timeout estendido.",
                step="zip",
                progress=81,
            )
            for index, session in enumerate(retry._session_candidates(primary), start=1):
                try:
                    return _direct_download_resilient(job_id, session)
                except Exception as direct_error:
                    if retry._is_credit_error(direct_error):
                        raise
                    first_error = direct_error
                    if not _is_transient_error(direct_error) and not retry._is_plugintheme_session_error(direct_error):
                        raise
                    if index < 2:
                        time.sleep(1.0)

        session, detail = _profile_http_session(primary)
        one_click._emit(
            job_id,
            f"Retry da sessão PluginTheme: {detail}",
            step="zip",
            progress=82,
        )
        if session is not None:
            try:
                return _direct_download_resilient(job_id, session)
            except Exception as direct_error:
                if retry._is_credit_error(direct_error):
                    raise
                first_error = direct_error
                is_session = retry._is_plugintheme_session_error(direct_error)
                is_transient = _is_transient_error(direct_error)

        if is_transient:
            raise RuntimeError(
                "PluginTheme respondeu com timeout/falha transitória mesmo após o retry de rede com timeout estendido. "
                "Não é necessário refazer descrição ou imagem: clique em Tentar novamente para retomar diretamente do ZIP."
            ) from first_error

        raise RuntimeError(
            "Sessão PluginTheme não confirmada mesmo após reler diretamente o perfil renovado. "
            "Clique em Renovar sessão PluginTheme, faça login, confirme que a área da conta está aberta e FECHE "
            "completamente a janela Chrome de renovação. Depois clique em Tentar novamente; descrição e imagem prontas "
            "serão reaproveitadas e o fluxo retomará do ZIP."
        ) from first_error


def install_addition_plugintheme_profile_recovery_policy() -> None:
    global _INSTALLED, _BASE_DOWNLOAD_SOURCE
    if _INSTALLED:
        return
    _BASE_DOWNLOAD_SOURCE = additions._download_source
    additions._download_source = _download_source_with_profile_recovery
    _INSTALLED = True
