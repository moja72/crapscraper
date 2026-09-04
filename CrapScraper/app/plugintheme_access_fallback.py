from __future__ import annotations

from pathlib import Path
from typing import Any

from app.updates.sources import SourceFailure

_INSTALLED = False


def _is_auth_access(error: SourceFailure) -> bool:
    detail = getattr(error, "error", None)
    return str(getattr(detail, "code", "") or "") == "authentication_access"


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
    if getattr(recovery, "_crapscraper_access_probe_file_fallback", False):
        _INSTALLED = True
        return

    original_cycle = recovery._download_cycle

    def cycle(source: Any, job: dict[str, Any], target: Path):
        try:
            return original_cycle(source, job, target)
        except SourceFailure as error:
            if not _is_auth_access(error):
                raise
            target.unlink(missing_ok=True)
            return _try_file_endpoint(source, job, target)

    recovery._download_cycle = cycle
    recovery._crapscraper_access_probe_file_fallback = True
    _INSTALLED = True


__all__ = ["install_plugintheme_access_fallback", "_try_file_endpoint"]
