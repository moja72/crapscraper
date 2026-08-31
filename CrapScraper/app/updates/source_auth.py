"""Shared authenticated source sessions supplied by the Playwright collector."""
from __future__ import annotations
from threading import RLock, Thread
from typing import Any
import asyncio
import os
import requests

_lock = RLock()
_sessions: dict[tuple[str, str], Any] = {}
_origins: dict[tuple[str, str], Any] = {}
_states: dict[tuple[str, str], str] = {}
_active_accounts: dict[str, str] = {}


def _source_key(source_kind: str) -> str:
    return str(source_kind or "").strip().lower()


def _account_key(account_key: str) -> str:
    return str(account_key or "").strip().lower()


def _configured_account(source_kind: str) -> str:
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
        created = requests.Session()
        created.headers.update({
            "User-Agent": str(getattr(browser.data, "user_agent", "") or "CrapScraper-update/1.0"),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": product_url,
        })
        for cookie in await browser.browser_context.cookies():
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
    created = _run(_browser_session(source, str(product_url or ""), account))
    register_source_session(source, created, account)
    set_source_state(source, "configured", account)
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
            _states[key] = "configured"
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
        if (source, account) in _sessions:
            _states[(source, account)] = state

def source_state(source_kind: str, account_key: str = "") -> str:
    source = _source_key(source_kind)
    account = _account_key(account_key)
    with _lock:
        account = account or _active_accounts.get(source, "")
        return _states.get((source, account), "not_configured")
