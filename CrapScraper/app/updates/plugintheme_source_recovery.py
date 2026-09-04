from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import requests

from app.updates.service import UpdateService
from app.updates.source_auth import (
    clear_source_session,
    ensure_source_session,
    get_source_account,
    get_source_session,
    set_source_state,
    source_state,
)
from app.updates.sources import (
    DownloadArtifact,
    PluginThemeSource,
    SourceFailure,
    classify_source_error,
)


_ORIGINAL_EXECUTION = UpdateService._execution
_AUTH_SOFT_BLOCKERS = {"source_not_validated", "source_unavailable"}


def _current_session(source: PluginThemeSource, account: str) -> Any | None:
    return get_source_session(source.kind, account) or get_source_session(source.kind)


def _session_is_live(source: PluginThemeSource, account: str) -> bool:
    return _current_session(source, account) is not None and source_state(source.kind, account) == "validated"


def _prime_session(source: PluginThemeSource, job: dict[str, Any]) -> Any | None:
    """Carrega a sessão persistente do PluginTheme apenas quando o usuário executa/prova a fonte."""
    account = get_source_account(source.kind)
    current = _current_session(source, account)
    if current is None:
        current = ensure_source_session(
            source.kind,
            str(job.get("source_url") or ""),
            account,
            allow_profile_probe=True,
        )
    source.validate_authentication()
    set_source_state(source.kind, "validated", account)
    return current or _current_session(source, account)


def _renew_session(source: PluginThemeSource, job: dict[str, Any]) -> Any | None:
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
        allow_profile_probe=True,
    )
    source.validate_authentication()
    set_source_state(source.kind, "validated", account)
    return renewed


def _requires_session_refresh(error: SourceFailure) -> bool:
    detail = getattr(error, "error", None)
    if detail is None:
        return False
    code = str(getattr(detail, "code", "") or "").lower()
    technical = str(getattr(detail, "technical_message", "") or "").lower()
    diagnosis = str(getattr(detail, "diagnosis", "") or "").lower()
    content_type = str(getattr(detail, "content_type", "") or "").lower()
    final_url = str(getattr(detail, "final_url", "") or "").lower()
    if code in {"authentication_access", "authentication_missing"}:
        return True
    if any(marker in final_url for marker in ("/login", "/auth/login", "wp-login")):
        return True
    if code == "source_download_failed" and "html" in content_type:
        return True
    evidence = f"{technical} {diagnosis}"
    return any(marker in evidence for marker in (
        "unauthorized", "forbidden", "não autentic", "nao autentic", "sessão expirada",
        "sessao expirada", "login necessário", "login necessario", "redirecionou para o login",
    ))


def _product_with_recovery(source: PluginThemeSource, job: dict[str, Any]) -> dict[str, str]:
    _prime_session(source, job)
    try:
        product = source._product(job)
    except SourceFailure as first_error:
        if not _requires_session_refresh(first_error):
            raise
        _renew_session(source, job)
        product = source._product(job)
    set_source_state(source.kind, "validated", get_source_account(source.kind))
    return product


def _json_payload(response: Any) -> Any:
    try:
        return response.json()
    except (ValueError, AttributeError):
        return None


def _access_allowed(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    current = value.get("data", value)
    if not isinstance(current, dict):
        return False
    allowed_keys = {"canDownload", "can_download", "hasAccess", "has_access", "allowed", "authorized"}
    for key, item in current.items():
        if key in allowed_keys and (item is True or str(item).strip().lower() in {"1", "true", "yes"}):
            return True
    return False


def _download_url(value: Any) -> str:
    preferred = {
        "downloadurl", "download_url", "signedurl", "signed_url", "fileurl", "file_url",
        "url", "download", "file",
    }
    if isinstance(value, str):
        text = value.strip()
        return text if text.startswith(("https://", "http://")) else ""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            compact = normalized.replace("_", "")
            if normalized in preferred or compact in preferred:
                found = _download_url(item)
                if found:
                    return found
        for item in value.values():
            found = _download_url(item)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _download_url(item)
            if found:
                return found
    return ""


def _response_meta(response: Any) -> tuple[int | None, str, str, str, str]:
    status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("Content-Type") or "").lower()
    disposition = str(headers.get("Content-Disposition") or "")
    final_url = str(getattr(response, "url", "") or "")
    text = str(getattr(response, "text", "") or "")
    return status, content_type, disposition, final_url, text


def _write_zip_bytes(
    response: Any,
    target: Path,
    *,
    source: PluginThemeSource,
    requested_url: str,
) -> DownloadArtifact:
    status, content_type, _disposition, final_url, text = _response_meta(response)
    body = bytes(getattr(response, "content", b"") or b"")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    if not body or not zipfile.is_zipfile(target):
        target.unlink(missing_ok=True)
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=status,
            body=text[:4096],
            requested_url=requested_url,
            final_url=final_url,
            content_type=content_type,
            technical="A resposta do endpoint de arquivo não contém um ZIP válido.",
        ))
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
    if bad:
        target.unlink(missing_ok=True)
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=status,
            requested_url=requested_url,
            final_url=final_url,
            content_type=content_type,
            technical=f"Entrada ZIP corrompida: {bad}",
        ))
    return DownloadArtifact(
        path=target,
        sha256=hashlib.sha256(body).hexdigest(),
        size=len(body),
        requested_url=requested_url,
        final_url=final_url or requested_url,
        content_type=content_type,
    )


def _download_signed_url(source: PluginThemeSource, url: str, target: Path) -> DownloadArtifact:
    account = get_source_account(source.kind)
    session = _current_session(source, account)
    if not isinstance(session, requests.Session):
        _prime_session(source, {"source_url": url})
        session = _current_session(source, account)
    if not isinstance(session, requests.Session):
        raise SourceFailure(classify_source_error(
            source.display_name,
            requested_url=url,
            technical="Sessão HTTP autenticada não ficou disponível para o download.",
        ))
    try:
        response = session.get(
            url,
            timeout=source.transport.timeout,
            allow_redirects=True,
            headers={"Referer": "https://plugintheme.net/"},
        )
    except requests.RequestException as error:
        raise SourceFailure(classify_source_error(
            source.display_name,
            requested_url=url,
            technical=str(error),
        )) from error
    status, content_type, _disposition, final_url, text = _response_meta(response)
    if status is not None and status >= 400:
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=status,
            body=text[:4096],
            requested_url=url,
            final_url=final_url,
            content_type=content_type,
        ))
    if "html" in content_type:
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=status,
            body=text[:4096],
            requested_url=url,
            final_url=final_url,
            content_type=content_type,
            technical="Resposta HTML recebida no lugar do ZIP do PluginTheme.",
        ))
    return _write_zip_bytes(response, target, source=source, requested_url=url)


def _download_cycle(source: PluginThemeSource, job: dict[str, Any], target: Path) -> DownloadArtifact:
    product = _product_with_recovery(source, job)
    check_url = f"{source.api_base}/downloads/{product['id']}/check-access"
    check = source._get(check_url)
    access = _json_payload(check)
    if not _access_allowed(access):
        serialized = json.dumps(access, ensure_ascii=False) if access is not None else str(getattr(check, "text", "") or "")
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=403,
            body=serialized,
            requested_url=check_url,
            final_url=str(getattr(check, "url", "") or check_url),
            content_type=str((getattr(check, "headers", {}) or {}).get("Content-Type") or ""),
            technical="Acesso ao produto não autorizado pelo PluginTheme.",
        ))

    file_url = f"{source.api_base}/downloads/{product['id']}/file"
    response = source._get(file_url)
    status, content_type, disposition, final_url, text = _response_meta(response)
    payload = _json_payload(response) if "json" in content_type or not ("zip" in content_type or ".zip" in disposition.lower()) else None

    # A API pode responder o próprio arquivo (inclusive application/octet-stream),
    # em vez do JSON com URL assinada. O fluxo antigo tratava esse caso como erro.
    if payload is None and "html" not in content_type:
        return _write_zip_bytes(response, target, source=source, requested_url=file_url)

    url = _download_url(payload)
    if not url:
        serialized = json.dumps(payload, ensure_ascii=False) if payload is not None else text[:4096]
        raise SourceFailure(classify_source_error(
            source.display_name,
            status=status,
            body=serialized,
            requested_url=file_url,
            final_url=final_url,
            content_type=content_type,
            technical="PluginTheme não retornou um arquivo ZIP nem uma URL de download válida.",
        ))
    return _download_signed_url(source, url, target)


def _validate_access(self: PluginThemeSource, job: dict[str, Any]) -> dict[str, str]:
    product = _product_with_recovery(self, job)
    return {
        "source_url": str(job["source_url"]),
        "product_id": product["id"],
        "version": product["version"],
    }


def _confirm_version(self: PluginThemeSource, job: dict[str, Any]) -> str:
    return _product_with_recovery(self, job)["version"]


def _download(self: PluginThemeSource, job: dict[str, Any], target: Path) -> DownloadArtifact:
    try:
        return _download_cycle(self, job, target)
    except SourceFailure as first_error:
        if not _requires_session_refresh(first_error):
            raise
        target.unlink(missing_ok=True)
        _renew_session(self, job)
        return _download_cycle(self, job, target)


def _execution(self: UpdateService, job: dict[str, Any]) -> dict[str, Any]:
    """Não desabilita PluginTheme apenas porque sua sessão ainda precisa ser carregada.

    A autenticação continua obrigatória e é provada imediatamente antes da execução,
    mas o botão deixa de depender de uma validação antiga guardada no painel.
    """
    result = dict(_ORIGINAL_EXECUTION(self, job))
    if str(job.get("source_kind") or "") != "plugintheme":
        return result
    blockers = list(result.get("blockers") or [])
    source_blockers = [item for item in blockers if str(item.get("code") or "") in _AUTH_SOFT_BLOCKERS]
    hard = [item for item in blockers if str(item.get("code") or "") not in _AUTH_SOFT_BLOCKERS]
    if source_blockers and not hard:
        try:
            from app.plugintheme_profile import profile_diagnostic
            evidence = profile_diagnostic(get_source_account("plugintheme"))
        except Exception:
            evidence = {}
        configured = bool(
            evidence.get("configured")
            or evidence.get("profile_exists")
            or evidence.get("storage_state_exists")
            or evidence.get("browser_storage_exists")
        )
        if configured:
            return {
                **result,
                "allowed": True,
                "preflight_required": True,
                "warnings": source_blockers,
                "blockers": [],
                "authentication_on_execute": True,
            }
    return result


def install_plugintheme_source_recovery() -> None:
    if getattr(PluginThemeSource, "_crapscraper_source_recovery_installed", False):
        return
    PluginThemeSource.validate_access = _validate_access
    PluginThemeSource.confirm_version = _confirm_version
    PluginThemeSource.download = _download
    PluginThemeSource._crapscraper_source_recovery_installed = True

    # performance_runtime já foi instalado quando este módulo é importado por
    # app.updates.__init__; portanto embrulhamos a versão final de _execution.
    if not getattr(UpdateService, "_crapscraper_plugintheme_execution_installed", False):
        UpdateService._execution = _execution
        UpdateService._crapscraper_plugintheme_execution_installed = True


__all__ = ["install_plugintheme_source_recovery"]
