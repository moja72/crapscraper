from __future__ import annotations

import time
from typing import Any

from app.updates import ultrapack_source_recovery as recovery
from app.updates.source_auth import get_source_account, get_source_session
from app.updates.sources import SourceFailure, UltraPackSource


_ORIGINAL_VALIDATE = UltraPackSource.validate_access
_ORIGINAL_CONFIRM = UltraPackSource.confirm_version
_CACHE: dict[str, dict[str, Any]] = {}
_TTL_SECONDS = 30.0


def _key(job: dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("comparison_item_id") or job.get("source_url") or "")


def _session(source: UltraPackSource) -> Any | None:
    account = get_source_account(source.kind)
    return get_source_session(source.kind, account) or get_source_session(source.kind)


def _get(source: UltraPackSource, job: dict[str, Any], *, consume: bool = False) -> dict[str, Any] | None:
    key = _key(job)
    item = _CACHE.get(key)
    if not key or not isinstance(item, dict):
        return None
    if time.monotonic() - float(item.get("at") or 0.0) > _TTL_SECONDS or int(item.get("session_id") or 0) != id(_session(source)):
        _CACHE.pop(key, None)
        return None
    if consume:
        _CACHE.pop(key, None)
    return item


def _put(source: UltraPackSource, job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    key = _key(job)
    if key:
        _CACHE[key] = {
            "at": time.monotonic(),
            "session_id": id(_session(source)),
            "download_url": str(payload.get("download_url") or ""),
            "version": str(payload.get("version") or ""),
        }
    return payload


def _validate(self: UltraPackSource, job: dict[str, Any]) -> dict[str, str]:
    cached = _get(self, job)
    if cached:
        return {
            "source_url": str(job.get("source_url") or ""),
            "download_url": str(cached.get("download_url") or ""),
            "version": str(cached.get("version") or ""),
        }
    return _put(self, job, dict(_ORIGINAL_VALIDATE(self, job)))


def _confirm(self: UltraPackSource, job: dict[str, Any]) -> str:
    cached = _get(self, job)
    if cached and str(cached.get("version") or ""):
        return str(cached["version"])
    return str(_ORIGINAL_CONFIRM(self, job) or "")


def _download(self: UltraPackSource, job: dict[str, Any], target):
    cached = _get(self, job, consume=True)
    if cached and str(cached.get("download_url") or ""):
        url = str(cached["download_url"])
    else:
        url, _version = recovery._inspect_with_recovery(self, job)
    try:
        return recovery._download_once(self, url, target)
    except SourceFailure as first_error:
        if not recovery._error_requires_session_refresh(first_error):
            raise
        target.unlink(missing_ok=True)
        _CACHE.pop(_key(job), None)
        recovery._renew_session(self, job)
        refreshed_url, _refreshed_version = recovery._inspect_with_recovery(self, job)
        return recovery._download_once(self, refreshed_url, target)


def install_ultrapack_fast_probe() -> None:
    if getattr(UltraPackSource, "_crapscraper_fast_probe_installed", False):
        return
    UltraPackSource.validate_access = _validate
    UltraPackSource.confirm_version = _confirm
    UltraPackSource.download = _download
    UltraPackSource._crapscraper_fast_probe_installed = True


install_ultrapack_fast_probe()

__all__ = ["install_ultrapack_fast_probe"]
