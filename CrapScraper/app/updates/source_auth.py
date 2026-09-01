"""Shared authenticated source sessions supplied by the Playwright collector."""
from __future__ import annotations
from threading import RLock, Thread
from typing import Any
import asyncio
import os
import requests
from urllib.parse import urlsplit

from app.plugintheme_profile import (
    ACCOUNT_URL,
    SUBSCRIPTION_URL,
    complete_manual_renewal,
    find_access_token,
    profile_diagnostic,
    renewal_pending,
    storage_state_path,
    stored_state,
)

_lock = RLock()
_sessions: dict[tuple[str, str], Any] = {}
_origins: dict[tuple[str, str], Any] = {}
_states: dict[tuple[str, str], str] = {}
_diagnostics: dict[tuple[str, str], dict[str, Any]] = {}
_active_accounts: dict[str, str] = {}


class PluginThemeAuthenticationError(RuntimeError):
    def __init__(self, message: str, diagnostic: dict[str, Any]):
        super().__init__(message)
        self.diagnostic = diagnostic


def _source_key(source_kind: str) -> str:
    return str(source_kind or "").strip().lower()


def _account_key(account_key: str) -> str:
    return str(account_key or "").strip().lower()


def _configured_account(source_kind: str) -> str:
    from app.collection.legacy_core import settings

    for account in ("coproducaolancamentos", "bernardes1992"):
        try:
            if settings.is_account_configured(account, source_kind):
                return account
        except (KeyError, ValueError):
            continue
    prefix = "SCRAPER_PLUGINTHEME" if source_kind == "plugintheme" else "SCRAPER_ULTRAPACKV2"
    for account in ("COPRODUCAOLANCAMENTOS", "BERNARDES1992"):
        if os.getenv(f"{prefix}_{account}_EMAIL", "").strip() and os.getenv(
            f"{prefix}_{account}_PASSWORD", ""
        ).strip():
            return account.lower()
    return ""


def _default_account() -> str:
    # O cadastro de contas da coleta é a fonte canônica também para os fluxos
    # que ainda não publicaram uma sessão em memória (painel recém-aberto).
    from app.collection.legacy_core import settings

    return str(settings.DEFAULT_ACCOUNT_KEY or "").strip().lower()


def _run(coroutine: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    result: list[Any] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as error:
            errors.append(error)

    thread = Thread(target=worker, name="update-source-auth", daemon=True)
    thread.start(); thread.join()
    if errors:
        raise errors[0]
    return result[0]


def _safe_url(value: str) -> str:
    parsed = urlsplit(str(value or ""))
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else str(value or "")


async def _http_session_from_browser(
    browser: Any,
    referer: str,
    site_key: str = "plugintheme",
) -> tuple[requests.Session, dict[str, Any]]:
    cookies = list(await browser.browser_context.cookies())
    provider_domain = "plugintheme.net" if site_key == "plugintheme" else "ultrapackv2.com"
    provider_cookies = [
        cookie for cookie in cookies
        if str(cookie.get("domain") or "").lstrip(".").lower().endswith(provider_domain)
    ]
    storage_rows: list[dict[str, Any]] = []
    try:
        storage_rows = list(await browser.page.evaluate(
            """() => {
              const rows = [];
              for (const [scope, store] of [['localStorage', window.localStorage], ['sessionStorage', window.sessionStorage]]) {
                for (let i = 0; i < store.length; i += 1) {
                  const key = store.key(i);
                  rows.push({scope, key, value: store.getItem(key) || ''});
                }
              }
              return rows;
            }"""
        ) or [])
    except Exception:
        storage_rows = []
    created = requests.Session()
    parsed_referer = urlsplit(referer)
    created.headers.update({
        "User-Agent": str(getattr(browser.data, "user_agent", "") or "CrapScraper-update/1.0"),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
    })
    if parsed_referer.scheme and parsed_referer.netloc:
        created.headers["Origin"] = f"{parsed_referer.scheme}://{parsed_referer.netloc}"
    for cookie in provider_cookies:
        name, value = str(cookie.get("name") or ""), str(cookie.get("value") or "")
        if not name or not value:
            continue
        try:
            created.cookies.set(
                name, value, domain=str(cookie.get("domain") or "") or None,
                path=str(cookie.get("path") or "/") or "/",
            )
        except Exception:
            created.cookies.set(name, value)
    token = ""
    for row in storage_rows:
        if isinstance(row, dict):
            token = find_access_token(row.get("value"))
            if token:
                break
    if token:
        created.headers["Authorization"] = f"Bearer {token}"
    evidence = {
        "cookie_count": len(provider_cookies),
        "httponly_cookie_count": sum(1 for cookie in provider_cookies if cookie.get("httpOnly")),
        "storage_entry_count": len(storage_rows),
        "access_token_present": bool(token),
    }
    return created, evidence


async def _validated_plugintheme_session(account_key: str) -> tuple[requests.Session, dict[str, Any]]:
    """Open the persistent profile and prove access to the protected account page."""
    from app.collection.legacy_core.browser import (
        AuthenticationState,
        close_browser_session,
        create_browser_session,
        determine_authentication_state,
    )

    diagnostic = profile_diagnostic(account_key)
    browser = None
    try:
        browser = await create_browser_session(
            None,
            site_key="plugintheme",
            item_type_key="plugin_theme",
            account_key=account_key,
            slot_name="default",
            headless=True,
            create_detail_page=False,
        )
        persisted = {} if renewal_pending(account_key) else stored_state(account_key)
        persisted_cookies = [
            cookie for cookie in persisted.get("cookies", [])
            if isinstance(cookie, dict)
            and str(cookie.get("domain") or "").lstrip(".").lower().endswith("plugintheme.net")
        ]
        if persisted_cookies:
            await browser.browser_context.add_cookies(persisted_cookies)
            diagnostic["storage_state_loaded"] = True
        await browser.goto(SUBSCRIPTION_URL)
        subscription_indicator = False
        wait_for_function = getattr(browser.page, "wait_for_function", None)
        if callable(wait_for_function):
            try:
                await wait_for_function(
                    """() => {
                      const path = String(location.pathname || '').toLowerCase();
                      const text = String(document.body?.innerText || '');
                      return path.includes('/account/subscription')
                        && /(planos ativos|active plans)/i.test(text)
                        && /(restantes|remaining)/i.test(text);
                    }""",
                    timeout=10_000,
                )
                subscription_indicator = True
            except Exception:
                subscription_indicator = False
        current_url = _safe_url(str(getattr(browser.page, "url", "") or ""))
        authentication = await determine_authentication_state(browser.page)
        http, evidence = await _http_session_from_browser(browser, SUBSCRIPTION_URL)
        login_redirect = "/auth/login" in current_url.lower()
        diagnostic.update({
            **evidence,
            "current_url": current_url,
            "login_redirect": login_redirect,
            "authenticated_indicator": authentication is AuthenticationState.AUTHENTICATED,
            "subscription_indicator": subscription_indicator,
            "authenticated": (
                authentication is AuthenticationState.AUTHENTICATED or subscription_indicator
            ) and not login_redirect,
        })
        if not diagnostic["authenticated"]:
            http.close()
            raise PluginThemeAuthenticationError(
                "Sessão PluginTheme inválida: a área protegida redirecionou para o login.",
                diagnostic,
            )
        state_path = storage_state_path(account_key)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        await browser.browser_context.storage_state(path=str(state_path))
        complete_manual_renewal(account_key)
        diagnostic.update({"storage_state_exists": True, "storage_state_saved": True})
        return http, diagnostic
    except PluginThemeAuthenticationError:
        raise
    except Exception as error:
        diagnostic.update({"authenticated": False, "probe_error": type(error).__name__})
        message = str(error).lower()
        if any(term in message for term in ("profile", "singleton", "in use", "processsingleton")):
            raise PluginThemeAuthenticationError(
                "O perfil PluginTheme está aberto. Feche a janela de renovação e verifique novamente.",
                diagnostic,
            ) from error
        raise PluginThemeAuthenticationError(
            f"Não foi possível validar funcionalmente a sessão PluginTheme ({type(error).__name__}).",
            diagnostic,
        ) from error
    finally:
        if browser is not None:
            await close_browser_session(browser)


async def _browser_session(
    source_kind: str,
    product_url: str,
    account_key: str,
    *,
    allow_manual_login: bool = False,
) -> requests.Session:
    from app.collection.legacy_core.browser import (
        close_browser_session,
        open_authenticated_browser_session,
    )

    site_key = "plugintheme" if source_kind == "plugintheme" else "ultrapackv2"
    browser = await open_authenticated_browser_session(
        None,
        None,
        site_key=site_key,
        item_type_key="plugin_theme" if site_key == "plugintheme" else "plugin",
        account_key=account_key,
        slot_name="default",
        # Consultas disparadas pelo backend nunca abrem uma janela nem aguardam
        # login humano. O fluxo explícito de renovação continua sendo o dono da
        # autenticação manual do PluginTheme.
        headless=not allow_manual_login,
        allow_manual_login=allow_manual_login,
        create_detail_page=False,
    )
    try:
        if product_url:
            await browser.goto(product_url)
        created, _evidence = await _http_session_from_browser(browser, product_url, site_key)
        return created
    finally:
        await close_browser_session(browser)


def ensure_source_session(
    source_kind: str,
    product_url: str = "",
    account_key: str = "",
    *,
    allow_profile_probe: bool = False,
) -> Any | None:
    """Cria sob demanda a sessao que Atualizar precisa, sem exigir Coletar antes."""
    source = _source_key(source_kind)
    account = _account_key(account_key)
    with _lock:
        if not account:
            account = _active_accounts.get(source, "")
        existing = _sessions.get((source, account)) if account else None
    if existing is not None:
        return existing
    # PluginTheme depende do perfil persistente e, quando expirado, exige uma
    # confirmacao humana. O preflight HTTP nao pode abrir uma janela e bloquear
    # a requisicao da interface por ate cinco minutos. A sessao continua sendo
    # publicada pelo fluxo de Coletar/renovacao explicita.
    if source == "plugintheme" and not allow_profile_probe:
        return None
    account = account or get_source_account(source)
    if not account:
        return None
    if source == "plugintheme":
        try:
            created, diagnostic = _run(_validated_plugintheme_session(account))
        except PluginThemeAuthenticationError as error:
            with _lock:
                _active_accounts[source] = account
                _states[(source, account)] = "expired"
                _diagnostics[(source, account)] = dict(error.diagnostic)
            raise
    else:
        created = _run(_browser_session(source, str(product_url or ""), account))
        diagnostic = {"authenticated": True, "current_url": _safe_url(product_url)}
    register_source_session(source, created, account)
    set_source_diagnostic(source, diagnostic, account)
    set_source_state(source, "validated", account)
    return get_source_session(source, account)

def register_source_session(source_kind: str, session: Any, account_key: str = "") -> None:
    if source_kind and session is not None:
        source = _source_key(source_kind)
        account = _account_key(account_key) or get_source_account(source)
        key = (source, account)
        with _lock:
            # Publica uma cópia independente da sessão do job. Assim o
            # encerramento da coleta não fecha o cliente usado por Atualizar.
            shared = requests.Session() if isinstance(session, requests.Session) else session
            if isinstance(session, requests.Session) and isinstance(shared, requests.Session):
                shared.trust_env = session.trust_env
                shared.headers.update(dict(session.headers))
                for cookie in session.cookies:
                    shared.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
            _sessions[key] = shared
            _origins[key] = session
            _states[key] = "validated"
            if source == "plugintheme" and isinstance(shared, requests.Session):
                provider_cookies = [
                    cookie for cookie in shared.cookies
                    if str(getattr(cookie, "domain", "") or "").lstrip(".").lower().endswith("plugintheme.net")
                ]
                _diagnostics[key] = {
                    **profile_diagnostic(account),
                    "authenticated": True,
                    "authenticated_indicator": True,
                    "login_redirect": False,
                    "cookie_count": len(provider_cookies),
                }
            _active_accounts[source] = account
        try:
            from app.credits import invalidate_credit_cache
            invalidate_credit_cache(source, account)
        except ImportError:
            pass

def get_source_account(source_kind: str) -> str:
    source = _source_key(source_kind)
    with _lock:
        active = _active_accounts.get(source, "")
    # O painel de créditos pode ser aberto antes de qualquer coleta publicar
    # uma sessão. Nesse caso a conta vazia deve apontar para a conta realmente
    # configurada, e nunca para a chave artificial ``default``.
    return active or _configured_account(source) or _default_account()


def get_source_session(source_kind: str, account_key: str = "") -> Any | None:
    source = _source_key(source_kind)
    account = _account_key(account_key)
    with _lock:
        if not account:
            account = _active_accounts.get(source, "")
        return _sessions.get((source, account)) if account else None


def clear_source_session(source_kind: str, session: Any | None = None, account_key: str = "") -> None:
    source = _source_key(source_kind)
    account = _account_key(account_key)
    removed_accounts: list[str] = []
    with _lock:
        candidates = [key for key in _sessions if key[0] == source and (not account or key[1] == account)]
        for key in candidates:
            current, origin = _sessions.get(key), _origins.get(key)
            if session is not None and current is not session and origin is not session:
                continue
            _sessions.pop(key, None)
            _origins.pop(key, None)
            _states.pop(key, None)
            _diagnostics.pop(key, None)
            removed_accounts.append(key[1])
        active = _active_accounts.get(source)
        if active in removed_accounts:
            remaining = next((key[1] for key in _sessions if key[0] == source), "")
            if remaining:
                _active_accounts[source] = remaining
            else:
                _active_accounts.pop(source, None)
    try:
        from app.credits import invalidate_credit_cache
        if removed_accounts:
            for removed in removed_accounts:
                invalidate_credit_cache(source, removed)
        else:
            invalidate_credit_cache(source, account)
    except ImportError:
        pass

def set_source_state(source_kind: str, state: str, account_key: str = "") -> None:
    source = _source_key(source_kind)
    account = _account_key(account_key)
    with _lock:
        account = account or _active_accounts.get(source, "")
        if account:
            _states[(source, account)] = state


def set_source_diagnostic(source_kind: str, diagnostic: dict[str, Any], account_key: str = "") -> None:
    source = _source_key(source_kind)
    account = _account_key(account_key) or get_source_account(source)
    if account:
        with _lock:
            _diagnostics[(source, account)] = dict(diagnostic)


def get_source_diagnostic(source_kind: str, account_key: str = "") -> dict[str, Any]:
    source = _source_key(source_kind)
    account = _account_key(account_key) or get_source_account(source)
    with _lock:
        return dict(_diagnostics.get((source, account), {}))

def source_state(source_kind: str, account_key: str = "") -> str:
    source = _source_key(source_kind)
    account = _account_key(account_key)
    with _lock:
        account = account or _active_accounts.get(source, "")
        return _states.get((source, account), "not_configured")
