from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.updates.source_auth import (
    clear_source_session,
    ensure_source_session,
    get_source_account,
    get_source_session,
    set_source_state,
)
from app.updates.sources import (
    DownloadArtifact,
    HttpDownloadTransport,
    SourceFailure,
    UltraPackSource,
)


def _error_requires_session_refresh(error: SourceFailure) -> bool:
    detail = getattr(error, "error", None)
    if detail is None:
        return False

    code = str(getattr(detail, "code", "") or "").strip().lower()
    technical = str(getattr(detail, "technical_message", "") or "").strip().lower()
    content_type = str(getattr(detail, "content_type", "") or "").strip().lower()
    final_url = str(getattr(detail, "final_url", "") or "").strip().lower()
    status = getattr(detail, "http_status", None)

    if code == "authentication_access":
        return True
    if code == "source_download_failed" and "html" in content_type:
        return True

    # O UltraPack usa um token ``data-f`` temporário/one-shot. Em alguns itens a
    # URL expira ou é consumida e o servidor continua respondendo HTTP 2xx, porém
    # entrega uma página/payload que não é ZIP. O downloader canônico valida os
    # bytes e classifica isso como source_download_failed. Uma única renovação de
    # sessão + redescoberta do data-f é segura e evita o falso terminal observado
    # em itens como Aoki. Créditos insuficientes têm código próprio e nunca entram
    # neste caminho.
    try:
        successful_http = status is not None and 200 <= int(status) < 300
    except (TypeError, ValueError):
        successful_http = False
    non_zip_markers = (
        "não é um zip válido",
        "nao e um zip valido",
        "não contém um zip válido",
        "nao contem um zip valido",
        "resposta da origem incompatível com um arquivo zip",
        "resposta da origem incompativel com um arquivo zip",
    )
    if (
        code == "source_download_failed"
        and successful_http
        and any(marker in technical for marker in non_zip_markers)
    ):
        return True

    if any(
        marker in technical
        for marker in (
            "botão autenticado de download não encontrado",
            "botao autenticado de download nao encontrado",
            "botão real de download não encontrado",
            "botao real de download nao encontrado",
            "resposta html recebida no lugar do zip",
        )
    ):
        return True
    return any(marker in final_url for marker in ("/login", "/auth/login"))


def _current_session(source: UltraPackSource, account: str) -> Any | None:
    return get_source_session(source.kind, account) or get_source_session(source.kind)


def _renew_session(source: UltraPackSource, job: dict[str, Any]) -> Any | None:
    account = get_source_account(source.kind)
    current = _current_session(source, account)
    if current is not None:
        clear_source_session(source.kind, current, account_key=account)
        close = getattr(current, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    set_source_state(source.kind, "expired", account)
    renewed = ensure_source_session(
        source.kind,
        str(job.get("source_url") or ""),
        account,
    )
    source.validate_authentication()
    return renewed


def _inspect_with_recovery(source: UltraPackSource, job: dict[str, Any]) -> tuple[str, str]:
    account = get_source_account(source.kind)
    ensure_source_session(
        source.kind,
        str(job.get("source_url") or ""),
        account,
    )
    source.validate_authentication()

    try:
        result = source._inspect(job)
    except SourceFailure as first_error:
        if not _error_requires_session_refresh(first_error):
            raise
        _renew_session(source, job)
        try:
            result = source._inspect(job)
        except SourceFailure:
            set_source_state(source.kind, "expired", account)
            raise

    set_source_state(source.kind, "validated", account)
    return result


def _validate_access(self: UltraPackSource, job: dict[str, Any]) -> dict[str, str]:
    """Valida a fonte e renova uma sessão UltraPack obsoleta uma única vez."""
    url, version = _inspect_with_recovery(self, job)
    return {
        "source_url": str(job["source_url"]),
        "download_url": url,
        "version": version,
    }


def _confirm_version(self: UltraPackSource, job: dict[str, Any]) -> str:
    return _inspect_with_recovery(self, job)[1]


def _download_once(
    source: UltraPackSource,
    url: str,
    target: Path,
) -> DownloadArtifact:
    account = get_source_account(source.kind)
    shared = _current_session(source, account)
    if isinstance(shared, requests.Session):
        return HttpDownloadTransport(
            session=shared,
            timeout=source.transport.timeout,
        ).download(
            url=url,
            target=target,
            source=source.display_name,
        )
    return source.transport.download(
        url=url,
        target=target,
        source=source.display_name,
    )


def _download(self: UltraPackSource, job: dict[str, Any], target: Path) -> DownloadArtifact:
    """Baixa com a sessão validada e só repete após evidência de sessão expirada.

    A segunda tentativa sempre redescobre o ``data-f`` em uma nova sessão. Isso evita
    reutilizar uma URL temporária/one-shot e também evita gastar crédito novamente
    quando a primeira falha não tem natureza de autenticação/token temporário.
    """
    url, _version = _inspect_with_recovery(self, job)
    try:
        return _download_once(self, url, target)
    except SourceFailure as first_error:
        if not _error_requires_session_refresh(first_error):
            raise

        target.unlink(missing_ok=True)
        _renew_session(self, job)
        refreshed_url, _refreshed_version = _inspect_with_recovery(self, job)
        return _download_once(self, refreshed_url, target)


def install_ultrapack_source_recovery() -> None:
    if getattr(UltraPackSource, "_crapscraper_session_recovery_installed", False):
        return

    UltraPackSource.validate_access = _validate_access
    UltraPackSource.confirm_version = _confirm_version
    UltraPackSource.download = _download
    UltraPackSource._crapscraper_session_recovery_installed = True


install_ultrapack_source_recovery()


__all__ = ["install_ultrapack_source_recovery"]
