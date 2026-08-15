"""Planejamento read-only da retencao de artefatos de atualizacao."""
from __future__ import annotations

from typing import Any, Mapping

from app import settings
from app.operations.models import JobState, OperationalJob


def build_cleanup_plan(job: OperationalJob, plan: Mapping[str, Any] | None) -> dict[str, Any]:
    candidate = dict(plan or {})
    current_path = str((candidate.get("current_zip") or {}).get("remote_path") or "")
    backup_path = str((candidate.get("backup") or {}).get("path") or job.backup_path)
    staging = candidate.get("remote_staging") or {}
    artifacts = [
        {"kind": "upload", "path": str(staging.get("upload_path") or "")},
        {"kind": "prepared", "path": str(staging.get("prepared_path") or "")},
    ]
    removable = [item for item in artifacts if item["path"]]
    safe = bool(
        job.state == JobState.COMPLETED
        and candidate.get("job_id") == job.job_id
        and current_path
        and backup_path
        and removable
        and all(job.job_id in item["path"] for item in removable)
        and all(item["path"] not in {current_path, backup_path} for item in removable)
    )
    return {
        "ready": safe,
        "execution_enabled": settings.UPDATE_REMOTE_CLEANUP_ENABLED,
        "automatic": False,
        "requires_explicit_action": True,
        "job_id": job.job_id,
        "retention_days": settings.UPDATE_BACKUP_RETENTION_DAYS,
        "backup_preserved": backup_path,
        "production_protected": current_path,
        "would_remove": removable if safe else [],
    }
