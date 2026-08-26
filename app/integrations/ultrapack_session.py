"""Compatibilidade para callers legados que ainda pedem uma sessão autenticada.

O fluxo final de Atualizar usa ``update_session`` diretamente. Este módulo existe
para os builders/callers antigos não quebrarem durante a migração e, ainda assim,
nunca considera um objeto Session como autenticação suficiente: a fonte precisa
confirmar acesso real ao produto.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.integrations.update_download import build_canonical_source_downloader
from app.integrations.wordpress import IntegrationError


@dataclass(frozen=True)
class AuthenticatedSession:
    session: Any
    source: str
    proof: str


def _probe(app: Any, product_url: str, source: str) -> AuthenticatedSession:
    session = getattr(
        app,
        "plugintheme_http_session" if source == "plugintheme" else "ultrapack_http_session",
        None,
    )
    if session is None and source == "plugintheme":
        try:
            from app.addition_plugintheme_profile_recovery_policy import _profile_http_session
            session, _detail = _profile_http_session(app)
        except Exception:
            session = None
    if session is None:
        raise IntegrationError(f"Sessão {source} indisponível")

    downloader = build_canonical_source_downloader(
        getattr(app, "ultrapack_http_session", None),
        getattr(app, "plugintheme_http_session", None),
    )
    downloader.session = session
    result = downloader.authentication_probe(product_url)
    if result.get("authenticated") is not True:
        raise IntegrationError(f"A fonte {source} não confirmou autenticação")

    if source == "plugintheme":
        setattr(app, "plugintheme_http_session", session)
    else:
        setattr(app, "ultrapack_http_session", session)
    return AuthenticatedSession(session, source, str(result.get("proof") or "source_probe"))


def get_authenticated_plugintheme_session(app: Any, product_url: str) -> AuthenticatedSession:
    return _probe(app, product_url, "plugintheme")


def get_authenticated_ultrapack_session(app: Any, product_url: str) -> AuthenticatedSession:
    return _probe(app, product_url, "ultrapack")


__all__ = [
    "AuthenticatedSession",
    "get_authenticated_plugintheme_session",
    "get_authenticated_ultrapack_session",
]
