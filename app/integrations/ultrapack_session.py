"""Sessões HTTP autenticadas usadas pelo fluxo de Atualizar.

Este módulo é uma ponte de compatibilidade para builders já existentes em
``app.web`` e ``new_product_workflow_policy``. A sessão só é devolvida depois de
uma prova real de acesso à fonte; simplesmente possuir um objeto requests.Session
ou abrir o navegador não é considerado autenticação suficiente.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Awaitable, TypeVar

import requests

from app import settings
from app.integrations.plugintheme_download import PluginThemeDownloader
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.wordpress import IntegrationError, sanitize_text


T = TypeVar("T")
_LOCKS = {
    "plugintheme": threading.RLock(),
    "ultrapack": threading.RLock(),
}


@dataclass(frozen=True)
class AuthenticatedSession:
    session: Any
    source: str
    authenticated: bool = True
    reused: bool = False
    current_url: str = ""
    proof: str = ""


def _context_value(app: Any, key: str, default: str = "") -> str:
    context = getattr(app, "context", None)
    if isinstance(context, dict):
        value = context.get(key, default)
    else:
        value = getattr(context, key, default)
    return str(value or default).strip()


def _remember(app: Any, source: str, session: Any) -> None:
    name = "plugintheme_http_session" if source == "plugintheme" else "ultrapack_http_session"
    for attr in (name, "_" + name):
        try:
            setattr(app, attr, session)
        except Exception:
            pass


def _existing(app: Any, source: str) -> Any:
    name = "plugintheme_http_session" if source == "plugintheme" else "ultrapack_http_session"
    return getattr(app, name, None) or getattr(app, "_" + name, None)


def _probe_ultrapack(session: Any, product_url: str) -> str:
    if session is None:
        raise IntegrationError("Sessão UltraPackV2 indisponível")
    downloader = UltrapackDownloader(session, timeout=20, retries=0)
    download_url, _version = downloader.inspect_product(product_url)
    if not str(download_url or "").strip():
        raise IntegrationError("A sessão UltraPackV2 não expôs o controle autorizado de download")
    return str(getattr(session, "_crapscraper_current_url", "") or product_url)


def _probe_plugintheme(session: Any, product_url: str) -> str:
    if session is None:
        raise IntegrationError("Sessão PluginTheme indisponível")
    response = session.get(product_url, timeout=20, allow_redirects=True)
    response.raise_for_status()
    final_url = str(getattr(response, "url", "") or product_url)
    if "/auth/login" in final_url.lower():
        raise IntegrationError("Sessão PluginTheme redirecionou para a página de login")
    product = PluginThemeDownloader.product_data(product_url, response.text)
    product_id = str(product.get("id") or "").strip()
    if not product_id:
        raise IntegrationError("PluginTheme não confirmou a identidade do produto autenticado")
    check = session.get(
        f"{PluginThemeDownloader.API_BASE}/downloads/{product_id}/check-access",
        timeout=20,
        allow_redirects=True,
        headers={"Referer": product_url, "Accept": "application/json,text/plain,*/*"},
    )
    check.raise_for_status()
    try:
        payload = check.json()
    except Exception as error:
        raise IntegrationError("PluginTheme retornou resposta inválida ao validar o acesso") from error
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if not PluginThemeDownloader.access_allowed(payload):
        raise IntegrationError("A API PluginTheme não autorizou o download deste produto")
    return final_url


def _probe(source: str, session: Any, product_url: str) -> str:
    return _probe_plugintheme(session, product_url) if source == "plugintheme" else _probe_ultrapack(session, product_url)


def _run_async(awaitable: Awaitable[T]) -> T:
    """Executa coroutine também quando o caller já possui event loop ativo."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: list[T] = []
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(awaitable))
        except BaseException as error:  # repassa exatamente ao caller síncrono
            errors.append(error)

    thread = threading.Thread(target=runner, name="update-source-session", daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result[0]


async def _browser_http_session(app: Any, source: str, product_url: str) -> tuple[requests.Session, str]:
    from app.browser import close_browser_session, open_authenticated_browser_session

    account_key = _context_value(app, "account_key", settings.DEFAULT_ACCOUNT_KEY)
    item_type_key = _context_value(app, "item_type_key", settings.DEFAULT_ITEM_TYPE_KEY)
    if source == "ultrapack" and item_type_key not in {"plugin", "theme", "template"}:
        item_type_key = "plugin"
    site_key = "plugintheme" if source == "plugintheme" else "ultrapackv2"
    control = getattr(app, "control", None)
    browser = await open_authenticated_browser_session(
        app,
        control,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=_context_value(app, "slot_name", settings.DEFAULT_SLOT_NAME),
        headless=settings.HEADLESS,
        allow_manual_login=(source == "plugintheme"),
        create_detail_page=False,
    )
    try:
        if product_url:
            await browser.goto(product_url, control=control, app=app)
        current_url = str(getattr(browser.page, "url", "") or product_url)
        cookies = await browser.browser_context.cookies()
        session = requests.Session()
        session.headers.update({
            "User-Agent": str(getattr(browser.data, "user_agent", "") or settings.PLAYWRIGHT_USER_AGENT),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": settings.HTTP_ACCEPT_LANGUAGE,
            "Referer": product_url or current_url,
        })
        for cookie in cookies or []:
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            if not name or not value:
                continue
            domain = str(cookie.get("domain") or "").strip() or None
            path = str(cookie.get("path") or "/") or "/"
            try:
                session.cookies.set(name, value, domain=domain, path=path)
            except Exception:
                session.cookies.set(name, value)
        setattr(session, "_crapscraper_current_url", current_url)
        return session, current_url
    finally:
        await close_browser_session(browser)


def _profile_plugintheme(app: Any) -> tuple[Any | None, str]:
    try:
        from app.addition_plugintheme_profile_recovery_policy import _profile_http_session
        return _profile_http_session(app)
    except Exception as error:
        return None, f"Falha ao reler o perfil PluginTheme: {sanitize_text(error)}"


def _get(app: Any, product_url: str, source: str) -> AuthenticatedSession:
    label = "PluginTheme" if source == "plugintheme" else "UltraPackV2"
    with _LOCKS[source]:
        current = _existing(app, source)
        if current is not None:
            try:
                current_url = _probe(source, current, product_url)
                return AuthenticatedSession(current, source, True, True, current_url, "source_access_probe")
            except Exception:
                try:
                    current.close()
                except Exception:
                    pass
                _remember(app, source, None)

        if source == "plugintheme":
            recovered, detail = _profile_plugintheme(app)
            if recovered is not None:
                try:
                    current_url = _probe(source, recovered, product_url)
                    _remember(app, source, recovered)
                    return AuthenticatedSession(recovered, source, True, False, current_url, "profile_access_probe")
                except Exception as error:
                    try:
                        recovered.close()
                    except Exception:
                        pass
                    detail = f"{detail} Validação do acesso falhou: {sanitize_text(error)}"
            # Se o perfil dedicado não estava utilizável, o browser padrão pode
            # renovar a sessão de forma explícita e depois exportar apenas cookies.
            try:
                browser_session, current_url = _run_async(_browser_http_session(app, source, product_url))
                current_url = _probe(source, browser_session, product_url)
                _remember(app, source, browser_session)
                return AuthenticatedSession(browser_session, source, True, False, current_url, "browser_access_probe")
            except Exception as error:
                raise IntegrationError(
                    f"Não foi possível autenticar no {label}. {detail} {sanitize_text(error)}".strip()
                ) from None

        try:
            browser_session, current_url = _run_async(_browser_http_session(app, source, product_url))
            current_url = _probe(source, browser_session, product_url)
            _remember(app, source, browser_session)
            return AuthenticatedSession(browser_session, source, True, False, current_url, "browser_access_probe")
        except Exception as error:
            raise IntegrationError(
                f"Não foi possível autenticar no {label}: {sanitize_text(error)}"
            ) from None


def get_authenticated_plugintheme_session(app: Any, product_url: str) -> AuthenticatedSession:
    return _get(app, product_url, "plugintheme")


def get_authenticated_ultrapack_session(app: Any, product_url: str) -> AuthenticatedSession:
    return _get(app, product_url, "ultrapack")


__all__ = [
    "AuthenticatedSession",
    "get_authenticated_plugintheme_session",
    "get_authenticated_ultrapack_session",
]
