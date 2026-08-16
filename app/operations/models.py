from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobState(str, Enum):
    APPROVED = "approved"
    PENDING = "pending"
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    STAGING = "staging"
    PREPARED = "prepared"
    PLANNED = "planned"
    PLAN_READY = "plan_ready"
    QUEUED = "queued"
    INSTALLING = "installing"
    FILESYSTEM_VALIDATED = "filesystem_validated"
    UPDATING_WORDPRESS = "updating_wordpress"
    VALIDATING_WORDPRESS = "validating_wordpress"
    VALIDATED = "validated"  # compatibilidade com dry-runs anteriores
    DRY_RUN_READY = "dry_run_ready"  # compatibilidade
    BLOCKED = "blocked"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    ROLLBACK_REQUIRED = "rollback_required"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    CANCELED = "canceled"


@dataclass
class OperationalJob:
    comparison_item_id: str
    woo_product_id: int
    name: str
    plugintema_version: str
    ultrapack_version: str
    ultrapack_url: str
    official_url: str
    decision: str
    relationship: str
    queue_type: str
    approved_source_version: str = ""
    effective_source_version: str = ""
    job_id: str = field(default_factory=lambda: str(uuid4()))
    state: JobState = JobState.APPROVED
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    diagnostics: list[str] = field(default_factory=list)
    prepared_at: str = ""
    executing_at: str = ""
    completed_at: str = ""
    last_completed_step: str = ""
    current_sha256: str = ""
    new_sha256: str = ""
    local_staging_path: str = ""
    remote_staging_path: str = ""
    backup_path: str = ""
    execution_error: str = ""
    execution_logs: list[str] = field(default_factory=list)
    version_write_evidence: dict[str, Any] = field(default_factory=dict)
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    queue_position: int = 0
    queue_name: str = "default"
    queued_at: str = ""
    attempts: int = 0
    canceled_at: str = ""
    source_name: str = ""
    initiated_by: str = ""
    manual_requested_at: str = ""

    def __post_init__(self) -> None:
        normalize_operational_job(self)

    def set_state(self, state: JobState, message: str = "") -> None:
        self.state = state
        self.updated_at = utc_now_iso()
        if message:
            self.diagnostics.append(message)


def normalize_operational_job(job: OperationalJob) -> OperationalJob:
    """Adiciona campos introduzidos depois a instancias materializadas antigas."""
    approved = str(getattr(job, "approved_source_version", "") or job.ultrapack_version)
    effective = str(getattr(job, "effective_source_version", "") or "")
    job.approved_source_version = approved
    job.effective_source_version = effective
    if not hasattr(job, "execution_error"):
        job.execution_error = ""
    if not hasattr(job, "execution_logs"):
        job.execution_logs = []
    if not hasattr(job, "version_write_evidence"):
        job.version_write_evidence = {}
    if not hasattr(job, "execution_history"):
        job.execution_history = []
    for name, default in (("queue_position", 0), ("queue_name", "default"), ("queued_at", ""),
                          ("attempts", 0), ("canceled_at", ""), ("source_name", ""),
                          ("initiated_by", ""), ("manual_requested_at", "")):
        if not hasattr(job, name):
            setattr(job, name, default)
    return job


def record_execution_outcome(
    job: OperationalJob, plan: dict[str, Any], result: str
) -> bool:
    """Registra um resultado sanitizado e idempotente do ciclo de execucao."""
    plan_id = str(plan.get("plan_id") or "")
    if any(
        isinstance(item, dict)
        and item.get("plan_id") == plan_id
        and item.get("executing_at") == job.executing_at
        for item in job.execution_history
    ):
        return False
    current = plan.get("current_zip") or {}
    fresh = plan.get("new_zip") or {}
    backup = plan.get("backup") or {}
    job.execution_history.append({
        "job_id": job.job_id,
        "comparison_item_id": job.comparison_item_id,
        "woo_product_id": job.woo_product_id,
        "product": job.name,
        "approved_source_version": job.approved_source_version,
        "effective_source_version": job.effective_source_version,
        "previous_site_version": str(plan.get("site_version") or job.plugintema_version),
        "prepared_at": job.prepared_at,
        "executing_at": job.executing_at,
        "completed_at": job.completed_at,
        "previous_sha256": str(current.get("sha256") or job.current_sha256),
        "new_sha256": str(fresh.get("sha256") or job.new_sha256),
        "backup_path": str(backup.get("path") or job.backup_path),
        "plan_id": plan_id,
        "result": str(result),
        "last_completed_step": job.last_completed_step,
        "source_name": str(getattr(job, "source_name", "") or ""),
        "initiated_by": str(getattr(job, "initiated_by", "") or ""),
        "recorded_at": utc_now_iso(),
    })
    return True


@dataclass
class DryRunPlan:
    job: OperationalJob
    product_id: int
    variation_ids: list[int]
    current_version: str
    target_version: str
    physical_file: str
    download_entries: list[dict[str, Any]]
    steps: list[str]
    payload_preview: dict[str, Any] | None = None
    physical_validation: dict[str, Any] | None = None
    write_blocked: bool = True
