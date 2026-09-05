from __future__ import annotations

from pathlib import Path
from typing import Any

from app.updates.models import UpdateError
from app.updates.sources import SourceFailure

_INSTALLED = False


def _is_auth_access(error: SourceFailure) -> bool:
    detail = getattr(error, "error", None)
    return str(getattr(detail, "code", "") or "") == "authentication_access"


def _is_missing_product(error: SourceFailure) -> bool:
    detail = getattr(error, "error", None)
    if detail is None:
        return False
    status = getattr(detail, "http_status", None)
    technical = str(getattr(detail, "technical_message", "") or "").lower()
    diagnosis = str(getattr(detail, "diagnosis", "") or "").lower()
    message = str(getattr(detail, "message", "") or "").lower()
    evidence = f"{technical} {diagnosis} {message}"
    if status == 404:
        return True
    return any(marker in evidence for marker in (
        "produto não encontrado no payload público do plugintheme",
        "produto nao encontrado no payload publico do plugintheme",
        "product not found",
        "produto não encontrado",
        "produto nao encontrado",
    ))


def _missing_product_failure(error: SourceFailure, job: dict[str, Any]) -> SourceFailure:
    detail = getattr(error, "error", None)
    requested = str(getattr(detail, "requested_url", "") or job.get("source_url") or "")
    technical = str(getattr(detail, "technical_message", "") or "")
    return SourceFailure(UpdateError(
        message="Produto não encontrado no PluginTheme; a aprovação desta fonte precisa ser revisada.",
        technical_message=technical or "A página/registro aprovado não existe mais no catálogo PluginTheme.",
        code="source_product_missing",
        stage="validating",
        source="PluginTheme",
        requested_url=requested,
        diagnosis="A fonte aprovada não possui um produto correspondente. O CrapScraper não troca silenciosamente para outra origem.",
        recoverable=False,
    ))


def _try_file_endpoint(source: Any, job: dict[str, Any], target: Path):
    from app.updates import plugintheme_source_recovery as recovery

    product = recovery._product_with_recovery(source, job)
    file_url = f"{source.api_base}/downloads/{product['id']}/file"
    response = source._get(file_url)
    status, content_type, disposition, final_url, text = recovery._response_meta(response)
    payload = recovery._json_payload(response) if "json" in content_type or not ("zip" in content_type or ".zip" in disposition.lower()) else None

    if payload is None and "html" not in content_type:
        return recovery._write_zip_bytes(response, target, source=source, requested_url=file_url)

    url = recovery._download_url(payload)
    if url:
        return recovery._download_signed_url(source, url, target)

    raise SourceFailure(recovery.classify_source_error(
        source.display_name,
        status=status,
        body=(str(payload) if payload is not None else text[:4096]),
        requested_url=file_url,
        final_url=final_url,
        content_type=content_type,
        technical="O check-access recusou o produto e o endpoint de arquivo também não forneceu ZIP ou URL válida.",
    ))


def install_plugintheme_access_fallback() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from app.updates import plugintheme_source_recovery as recovery

    if not getattr(recovery, "_crapscraper_missing_product_classification", False):
        original_product = recovery._product_with_recovery

        def product_with_presence(source: Any, job: dict[str, Any]):
            try:
                return original_product(source, job)
            except SourceFailure as error:
                if _is_missing_product(error):
                    raise _missing_product_failure(error, job) from None
                raise

        recovery._product_with_recovery = product_with_presence
        recovery._crapscraper_missing_product_classification = True

    if getattr(recovery, "_crapscraper_access_probe_file_fallback", False):
        _INSTALLED = True
        return

    original_cycle = recovery._download_cycle

    def cycle(source: Any, job: dict[str, Any], target: Path):
        try:
            return original_cycle(source, job, target)
        except SourceFailure as error:
            if _is_missing_product(error):
                raise _missing_product_failure(error, job) from None
            if not _is_auth_access(error):
                raise
            target.unlink(missing_ok=True)
            return _try_file_endpoint(source, job, target)

    recovery._download_cycle = cycle
    recovery._crapscraper_access_probe_file_fallback = True
    _INSTALLED = True


__all__ = ["install_plugintheme_access_fallback", "_try_file_endpoint", "_is_missing_product"]
