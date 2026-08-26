"""Validação concreta e recuperação previsível de sessões do fluxo Atualizar."""
from __future__ import annotations

import threading
from contextlib import suppress
from typing import Any, Callable
from urllib.parse import urlparse

from app.integrations.update_download import CanonicalSourceDownloader
from app.integrations.wordpress import IntegrationError, sanitize_text


_LOCKS = {"plugintheme": threading.RLock(), "ultrapack": threading.RLock()}


class UpdateSessionError(IntegrationError):
    def __init__(self, message: str, *, source: str, global_block: bool = True) -> None:
        super().__init__(message)
        self.source = source
        self.global_block = bool(global_block)
        self.category = "authentication"


def source_key(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return "plugintheme" if host in {"plugintheme.net", "www.plugintheme.net"} else "ultrapack"


def _attr(source: str) -> str:
    return "plugintheme_http_session" if source == "plugintheme" else "ultrapack_http_session"


def invalidate_update_session(app: Any, url_or_source: str) -> None:
    source = url_or_source if url_or_source in _LOCKS else source_key(url_or_source)
    for name in (_attr(source), "_" + _attr(source)):
        with suppress(Exception):
            setattr(app, name, None)


def _probe(
    downloader: CanonicalSourceDownloader,
    session: Any,
    product_url: str,
) -> dict[str, Any]:
    if session is None:
        raise UpdateSessionError(
            "Nenhuma sessão HTTP autenticada está disponível para a fonte.",
            source=source_key(product_url),
        )
    downloader.session = session
    result = dict(downloader.authentication_probe(product_url) or {})
    if result.get("authenticated") is not True:
        raise UpdateSessionError(
            "A fonte não confirmou autenticação e acesso ao produto.",
            source=source_key(product_url),
        )
    return result


def _recover_plugintheme_profile(app: Any) -> tuple[Any | None, str]:
    try:
        from app.addition_plugintheme_profile_recovery_policy import _profile_http_session
    except Exception as error:
        return None, f"Leitor do perfil PluginTheme indisponível: {type(error).__name__}."
    try:
        return _profile_http_session(app)
    except Exception as error:
        return None, f"Falha ao reler o perfil PluginTheme: {sanitize_text(error)}"


def _recover_ultrapack_legacy_provider(app: Any, product_url: str) -> tuple[Any | None, str]:
    try:
        from app.integrations.ultrapack_session import get_authenticated_ultrapack_session
    except Exception:
        return None, ""
    try:
        result = get_authenticated_ultrapack_session(app, product_url)
        return getattr(result, "session", result), "Sessão UltraPack renovada pelo bridge existente."
    except Exception as error:
        return None, sanitize_text(error)


def get_authenticated_update_session(
    app: Any,
    product_url: str,
    downloader: CanonicalSourceDownloader,
    *,
    logger: Callable[[str], None] | None = None,
) -> Any:
    log = logger or (lambda _message: None)
    source = source_key(product_url)
    label = "PluginTheme" if source == "plugintheme" else "UltraPackV2"

    with _LOCKS[source]:
        existing = getattr(app, _attr(source), None)
        if existing is not None:
            try:
                proof = _probe(downloader, existing, product_url)
                log(f"✅ Sessão {label} validada por acesso real ao produto ({proof.get('proof') or 'probe'}).")
                return existing
            except Exception as error:
                log(f"⚠ Sessão {label} em memória não passou na validação: {sanitize_text(error)}")
                invalidate_update_session(app, source)

        if source == "plugintheme":
            recovered, detail = _recover_plugintheme_profile(app)
        else:
            recovered, detail = _recover_ultrapack_legacy_provider(app, product_url)

        if recovered is not None:
            try:
                proof = _probe(downloader, recovered, product_url)
                setattr(app, _attr(source), recovered)
                log(f"✅ Sessão {label} recuperada e validada ({proof.get('proof') or 'probe'}).")
                return recovered
            except Exception as error:
                detail = f"{detail} Validação posterior falhou: {sanitize_text(error)}".strip()
                invalidate_update_session(app, source)

        if detail:
            log(f"⚠ {detail}")
        raise UpdateSessionError(
            f"Autenticação {label} indisponível. A sessão não foi confirmada por sinais reais do site; "
            "renove/conclua o login da fonte e tente novamente.",
            source=source,
            global_block=True,
        )
