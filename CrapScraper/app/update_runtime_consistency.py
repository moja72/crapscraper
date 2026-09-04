from __future__ import annotations

import hashlib
import os
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


_INSTALLED = False
_MANUAL_CACHE: dict[str, tuple[int, set[str]]] = {}
_COMPARISON_DB_MTIME: dict[str, int] = {}


def _version_key(value: Any) -> tuple[int, ...]:
    import re

    parts = [int(part) for part in re.findall(r"\d+", str(value or ""))]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts) or (0,)


def _update_db_for(path: Path) -> Path | None:
    configured = os.getenv("SCRAPER_UPDATE_DB_PATH", "").strip()
    if configured:
        candidate = Path(configured).resolve()
        return candidate if candidate.is_file() else None
    current = path.resolve()
    parents = [current] if current.is_dir() else [current.parent]
    parents += list(current.parents)
    seen: set[Path] = set()
    for parent in parents:
        if parent in seen:
            continue
        seen.add(parent)
        candidate = parent / "consolidated_updates.sqlite3"
        if candidate.is_file():
            return candidate
    return None


def _store_db_for(update_db: Path) -> Path:
    configured = os.getenv("SCRAPER_STORE_DB_PATH", "").strip()
    return Path(configured).resolve() if configured else update_db.parent / "consolidated_store.sqlite3"


def _manual_attempt_ids(update_db: Path) -> set[str]:
    store_db = _store_db_for(update_db)
    if not store_db.is_file():
        return set()
    try:
        mtime = store_db.stat().st_mtime_ns
    except OSError:
        return set()
    key = str(store_db)
    cached = _MANUAL_CACHE.get(key)
    if cached and cached[0] == mtime:
        return set(cached[1])
    try:
        with sqlite3.connect(store_db) as db:
            rows = db.execute(
                "SELECT attempt_id FROM store_monitor_requests "
                "WHERE attempt_id<>'' AND state IN ('completed','already_updated')"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return set()
    values = {str(row[0]) for row in rows if str(row[0] or "")}
    _MANUAL_CACHE[key] = (mtime, values)
    return values


def _completed_overrides(path: Path) -> dict[int, str]:
    update_db = _update_db_for(path)
    if update_db is None:
        return {}
    try:
        with sqlite3.connect(update_db) as db:
            rows = db.execute(
                "SELECT woo_product_id,current_version,source_version,stage "
                "FROM update_jobs WHERE public_state='success'"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return {}
    result: dict[int, str] = {}
    for product_id, current, target, stage in rows:
        if str(stage or "") not in {"completed", "already_current"}:
            continue
        values = [str(current or "").strip(), str(target or "").strip()]
        values = [value for value in values if value]
        if not values:
            continue
        effective = max(values, key=_version_key)
        pid = int(product_id or 0)
        previous = result.get(pid, "")
        if pid > 0 and (not previous or _version_key(effective) > _version_key(previous)):
            result[pid] = effective
    return result


def _patch_download_transport() -> None:
    from app.updates.sources import (
        DownloadArtifact,
        HttpDownloadTransport,
        SourceFailure,
        classify_source_error,
    )

    if getattr(HttpDownloadTransport, "_crapscraper_binary_zip_installed", False):
        return

    def download(
        self: Any,
        *,
        url: str,
        target: Path,
        source: str,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> DownloadArtifact:
        if urlparse(url).scheme not in {"http", "https"}:
            from app.updates.models import UpdateError
            raise SourceFailure(UpdateError(
                message=f"URL inválida para {source}.", code="invalid_source_url",
                stage="validating", source=source, requested_url=url, recoverable=False,
            ))
        try:
            response = self.session.get(
                url, headers=headers or {}, cookies=cookies or {}, timeout=self.timeout,
                allow_redirects=True, stream=True,
            )
        except requests.RequestException as error:
            raise SourceFailure(classify_source_error(
                source, requested_url=url, technical=str(error),
            )) from error

        content_type = str(response.headers.get("Content-Type") or "").lower()
        if response.status_code >= 400 or "html" in content_type:
            preview = response.content[:4096]
            raise SourceFailure(classify_source_error(
                source, status=response.status_code,
                body=preview.decode("utf-8", "ignore"), requested_url=url,
                final_url=str(response.url or ""), content_type=content_type,
                technical="Resposta HTML/HTTP recebida no lugar do arquivo de atualização." if "html" in content_type else "",
            ))

        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        preview = bytearray()
        try:
            with target.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    if len(preview) < 4096:
                        preview.extend(chunk[: 4096 - len(preview)])
                    stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if size <= 0 or not zipfile.is_zipfile(target):
                body = bytes(preview).decode("utf-8", "ignore")
                target.unlink(missing_ok=True)
                raise SourceFailure(classify_source_error(
                    source, status=response.status_code, body=body,
                    requested_url=url, final_url=str(response.url or ""),
                    content_type=content_type,
                    technical=(
                        "A resposta HTTP 2xx foi recebida, mas o conteúdo não é um ZIP válido. "
                        f"Content-Type informado: {content_type or 'ausente'}."
                    ),
                ))
            with zipfile.ZipFile(target) as archive:
                bad = archive.testzip()
            if bad:
                target.unlink(missing_ok=True)
                raise SourceFailure(classify_source_error(
                    source, status=response.status_code, requested_url=url,
                    final_url=str(response.url or ""), content_type=content_type,
                    technical=f"Entrada ZIP corrompida: {bad}",
                ))
        except SourceFailure:
            raise
        except Exception:
            target.unlink(missing_ok=True)
            raise

        return DownloadArtifact(
            path=target, sha256=digest.hexdigest(), size=size,
            requested_url=url, final_url=str(response.url or url), content_type=content_type,
        )

    HttpDownloadTransport.download = download
    HttpDownloadTransport._crapscraper_binary_zip_installed = True


def _patch_repository_consistency() -> None:
    from app.updates.repository import UpdateRepository

    if getattr(UpdateRepository, "_crapscraper_version_consistency_installed", False):
        return
    original_materialize = UpdateRepository.materialize
    original_finish = UpdateRepository.finish

    def repair_completed(self: Any) -> None:
        now_sql = "updated_at"
        with self.connection() as db:
            rows = db.execute(
                "SELECT job_id,current_version,source_version FROM update_jobs "
                "WHERE public_state='success' AND stage IN ('completed','already_current')"
            ).fetchall()
            for row in rows:
                current = str(row["current_version"] or "")
                target = str(row["source_version"] or "")
                effective = target if _version_key(target) > _version_key(current) else current
                if effective and effective != current:
                    db.execute(
                        f"UPDATE update_jobs SET current_version=?, {now_sql}={now_sql} WHERE job_id=?",
                        (effective, str(row["job_id"])),
                    )

    def materialize(self: Any, approvals: list[dict[str, Any]]) -> dict[str, int]:
        result = original_materialize(self, approvals)
        repair_completed(self)
        return result

    def finish(self: Any, job_id: str, attempt_id: str, **kwargs: Any) -> None:
        original_finish(self, job_id, attempt_id, **kwargs)
        if kwargs.get("success") and str(kwargs.get("stage") or "") in {"completed", "already_current"}:
            repair_completed(self)

    UpdateRepository.materialize = materialize
    UpdateRepository.finish = finish
    UpdateRepository.repair_completed_versions = repair_completed
    UpdateRepository._crapscraper_version_consistency_installed = True


def _patch_retry_and_origin() -> None:
    from app.current_app_recovery import _validate_base_environment, _validate_job_source
    from app.updates.service import UpdateService

    if getattr(UpdateService, "_crapscraper_retry_consistency_installed", False):
        return
    original_with_execution = UpdateService._with_execution

    def retry(self: Any, job_id: str) -> dict[str, Any]:
        _validate_base_environment(self)
        job = self.repository.get(job_id)
        kind = str(job.get("source_kind") or "")
        source_state = (self.environment_validation.get("sources") or {}).get(kind) or {}
        if not source_state.get("ok"):
            try:
                _validate_job_source(self, job, fresh=False)
            except Exception:
                _validate_job_source(self, job, fresh=True)
        self._require_execution_environment()
        self._require_job_execution(job_id)
        return self.executor.execute(job_id)

    def with_execution(self: Any, job: dict[str, Any]) -> dict[str, Any]:
        item = original_with_execution(self, job)
        item["execution_origin"] = "panel"
        item["execution_origin_label"] = "Painel"
        update_db = Path(self.repository.path)
        manual_attempts = _manual_attempt_ids(update_db)
        if manual_attempts:
            attempts = list(self.repository.history(str(item.get("job_id") or "")) or [])
            successful = [
                attempt for attempt in attempts
                if str(attempt.get("result") or "") == "success"
                and any(
                    isinstance(stage, dict) and str(stage.get("stage") or "") == "completed"
                    for stage in list(attempt.get("stages") or [])
                )
            ]
            if successful:
                latest = max(successful, key=lambda value: int(value.get("attempt_number") or 0))
                if str(latest.get("attempt_id") or "") in manual_attempts:
                    item["execution_origin"] = "manual"
                    item["execution_origin_label"] = "Manual"
        return item

    UpdateService.retry = retry
    UpdateService._with_execution = with_execution
    UpdateService._crapscraper_retry_consistency_installed = True


def _patch_comparison_versions() -> None:
    from app.comparison import matching

    if getattr(matching, "_crapscraper_live_version_overlay_installed", False):
        return
    original_full = matching._build_full_comparison
    original_payload = matching.build_comparison_payload

    def full(source_path: Path, site_path: Path) -> dict[str, Any]:
        payload = original_full(source_path, site_path)
        rows = list(payload.get("rows") or [])
        overrides = _completed_overrides(Path(site_path))
        changed = False
        for row in rows:
            product_id = int(row.get("woo_product_id") or row.get("site_id") or 0)
            current = overrides.get(product_id, "")
            if not current or _version_key(current) <= _version_key(row.get("site_version")):
                continue
            row["site_version"] = current
            status, reason, comparison = matching._build_status(
                row.get("source_version", ""), current,
            )
            action, action_label = matching._recommended_action_for_status(status)
            row.update({
                "status": status,
                "status_label": matching._STATUS_LABELS[status],
                "status_reason": reason,
                "version_comparison": comparison,
                "recommended_action": action,
                "recommended_action_label": action_label,
                "site_version_source": "CrapScraper",
            })
            changed = True
        if changed:
            counts = Counter(str(row.get("status") or "") for row in rows)
            for status, count in counts.items():
                if status in payload and isinstance(payload.get(status), int):
                    payload[status] = count
                key = f"{status}_total"
                if key in payload and isinstance(payload.get(key), int):
                    payload[key] = count
            if isinstance(payload.get("counts"), dict):
                payload["counts"].update(counts)
        payload["rows"] = rows
        return payload

    def build_comparison_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        site_path = Path(kwargs.get("site_path") or "")
        update_db = _update_db_for(site_path) if str(site_path) else None
        if update_db is not None:
            try:
                mtime = update_db.stat().st_mtime_ns
            except OSError:
                mtime = 0
            cache_key = str(update_db)
            if _COMPARISON_DB_MTIME.get(cache_key) != mtime:
                matching._CACHE_KEY = None
                matching._CACHE_PAYLOAD = None
                _COMPARISON_DB_MTIME[cache_key] = mtime
        return original_payload(*args, **kwargs)

    matching._build_full_comparison = full
    matching.build_comparison_payload = build_comparison_payload
    matching._crapscraper_live_version_overlay_installed = True


def install_update_runtime_consistency() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_download_transport()
    _patch_repository_consistency()
    _patch_retry_and_origin()
    _patch_comparison_versions()
    _INSTALLED = True


__all__ = [
    "install_update_runtime_consistency",
    "_completed_overrides",
    "_manual_attempt_ids",
]
