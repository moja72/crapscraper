"""Shared authenticated source sessions supplied by the Playwright collector."""
from __future__ import annotations
from threading import RLock
from typing import Any
import requests

_lock = RLock()
_sessions: dict[str, Any] = {}
_origins: dict[str, Any] = {}
_states: dict[str, str] = {}

def register_source_session(source_kind: str, session: Any) -> None:
    if source_kind and session is not None:
        with _lock:
            # Publica uma cópia independente da sessão do job. Assim o
            # encerramento da coleta não fecha o cliente usado por Atualizar.
            shared = requests.Session() if isinstance(session, requests.Session) else session
            if isinstance(session, requests.Session) and isinstance(shared, requests.Session):
                shared.trust_env = session.trust_env
                shared.headers.update(dict(session.headers))
                for cookie in session.cookies:
                    shared.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
            _sessions[str(source_kind).strip().lower()] = shared
            _origins[str(source_kind).strip().lower()] = session
            _states[str(source_kind).strip().lower()] = "configured"
        try:
            from app.credits import invalidate_credit_cache
            invalidate_credit_cache(source_kind)
        except ImportError:
            pass

def get_source_session(source_kind: str) -> Any | None:
    with _lock:
        return _sessions.get(str(source_kind or "").strip().lower())

def clear_source_session(source_kind: str, session: Any | None = None) -> None:
    key = str(source_kind or "").strip().lower()
    with _lock:
        current = _sessions.get(key)
        origin = _origins.get(key)
        if current is not None and (session is None or current is session or origin is session):
            _sessions.pop(key, None)
            _origins.pop(key, None)
            _states.pop(key, None)
    try:
        from app.credits import invalidate_credit_cache
        invalidate_credit_cache(key)
    except ImportError:
        pass

def set_source_state(source_kind: str, state: str) -> None:
    with _lock:
        if str(source_kind).strip().lower() in _sessions:
            _states[str(source_kind).strip().lower()] = state

def source_state(source_kind: str) -> str:
    with _lock:
        return _states.get(str(source_kind or "").strip().lower(), "not_configured")
