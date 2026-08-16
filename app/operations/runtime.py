"""Registro em memória dos jobs materializados para a sessão do painel."""
from __future__ import annotations

from threading import RLock
from typing import Any, Iterable, Mapping
import json
from dataclasses import fields
from pathlib import Path
import csv
import re
from app import settings
from app.operations.models import (
    JobState, OperationalJob, normalize_operational_job, record_execution_outcome,
)
from app.operations.queue import materialize_queue
from app.operations.cleanup_policy import build_cleanup_plan

_LOCK = RLock()
_JOBS: dict[str, OperationalJob] = {}
_PREVIEWS: dict[str, dict[str, Any]] = {}
_PLANS: dict[str, dict[str, Any]] = {}
_DISMISSED_HISTORY: dict[str, str] = {}
_QUEUE_CONTROL: dict[str, Any] = {"status": "stopped", "updated_at": "", "active_queue": "default", "queues": {"default": {"created_at": "", "updated_at": ""}}}

SAFE_EXECUTION_RELATIONSHIPS = frozenset({"safe_auto", "manual_confirmed"})
HISTORY_STATES = frozenset({
    JobState.COMPLETED, JobState.ROLLED_BACK, JobState.ERROR, JobState.FAILED,
    JobState.BLOCKED, JobState.ROLLBACK_REQUIRED, JobState.CANCELED, JobState.INTERRUPTED,
})


def _archive_previous_execution(job: OperationalJob) -> bool:
    if not (job.execution_error or job.execution_logs or job.version_write_evidence):
        return False
    job.execution_history.append({
        "executing_at": job.executing_at, "completed_at": job.completed_at,
        "last_completed_step": job.last_completed_step, "error": job.execution_error,
        "logs": list(job.execution_logs),
        "version_write_evidence": dict(job.version_write_evidence),
        "archived_at": job.updated_at,
    })
    job.execution_error = ""
    job.execution_logs = []
    job.version_write_evidence = {}
    job.executing_at = ""
    job.completed_at = ""
    job.last_completed_step = ""
    return True


def _numeric_version(value: str) -> tuple[int, ...] | None:
    parts = str(value or "").strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _is_newer_version(candidate: str, installed: str) -> bool:
    left, right = _numeric_version(candidate), _numeric_version(installed)
    if left is None or right is None:
        return False
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def _ensure_final_history(job: OperationalJob) -> bool:
    if job.state not in {JobState.COMPLETED, JobState.ROLLED_BACK,
                         JobState.ERROR, JobState.FAILED, JobState.ROLLBACK_REQUIRED}:
        return False
    plan = _PLANS.get(job.job_id) or {}
    return bool(plan) and record_execution_outcome(job, plan, job.state.value)


def is_execution_eligible(
    job: OperationalJob,
    preview: Mapping[str, Any] | None,
    plan: Mapping[str, Any] | None,
    *,
    enabled: bool | None = None,
    allowed_product_ids: frozenset[int] | None = None,
) -> bool:
    """Regra única usada pela UI e pela rota antes de iniciar uma execução."""
    execution_enabled = settings.UPDATE_EXECUTION_ENABLED if enabled is None else bool(enabled)
    allowed = (settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS
               if allowed_product_ids is None else frozenset(allowed_product_ids))
    candidate_plan = plan or {}
    local_path = str(candidate_plan.get("new_zip", {}).get("local_staging_path") or "")
    planned_backup = str(candidate_plan.get("backup", {}).get("path") or "")
    retryable = bool(
        job.state == JobState.ERROR
        and job.last_completed_step in {"backup_validated", "staging_upload_validated"}
        and planned_backup
        and job.backup_path == planned_backup
    )
    return bool(
        execution_enabled
        and (job.state in {JobState.PLAN_READY, JobState.QUEUED} or retryable)
        and (preview or {}).get("ready") is True
        and candidate_plan.get("ready") is True
        and candidate_plan.get("job_id") == job.job_id
        and int(candidate_plan.get("woo_product_id") or 0) == job.woo_product_id
        and job.relationship in SAFE_EXECUTION_RELATIONSHIPS
        and (not allowed or job.woo_product_id in allowed)
        and local_path and Path(local_path).is_file()
    )

def _record(job: OperationalJob) -> dict[str, Any]:
    data = {item.name: getattr(job, item.name) for item in fields(OperationalJob)}
    data["state"] = job.state.value
    return data

def _persist() -> None:
    path = Path(settings.UPDATE_RUNTIME_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": [_record(job) for job in _JOBS.values()],
               "previews": _PREVIEWS, "plans": _PLANS,
               "queue_control": _QUEUE_CONTROL,
               "dismissed_history": _DISMISSED_HISTORY}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    _persist_queue_spreadsheets()

def _queue_slug(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name or "default").strip()).strip("-")
    return cleaned[:80] or "default"

def _persist_queue_spreadsheets() -> None:
    directory = Path(settings.UPDATE_QUEUES_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    queues = dict(_QUEUE_CONTROL.get("queues") or {})
    queues.setdefault("default", {})
    headers = ["queue_name", "position", "job_id", "woocommerce_id", "product", "state",
               "source", "previous_version", "new_version", "requested_at", "queued_at",
               "updated_at", "completed_at", "result", "last_completed_step"]
    for name in queues:
        target = directory / f"{_queue_slug(name)}.csv"
        temporary = target.with_suffix(".csv.tmp")
        rows = sorted((job for job in _JOBS.values() if getattr(job, "queue_name", "default") == name), key=lambda job: (job.queue_position or 10**9, job.queued_at, job.created_at))
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            for job in rows:
                writer.writerow({"queue_name": name, "position": job.queue_position, "job_id": job.job_id,
                                 "woocommerce_id": job.woo_product_id, "product": job.name,
                                 "state": job.state.value, "source": getattr(job, "source_name", ""),
                                 "previous_version": job.plugintema_version,
                                 "new_version": job.effective_source_version or job.approved_source_version,
                                 "requested_at": getattr(job, "manual_requested_at", ""),
                                 "queued_at": job.queued_at, "updated_at": job.updated_at,
                                 "completed_at": job.completed_at,
                                 "result": job.execution_error or (job.diagnostics[-1] if job.diagnostics else ""),
                                 "last_completed_step": job.last_completed_step})
        temporary.replace(target)

def _normalize_queue_control() -> None:
    active = str(_QUEUE_CONTROL.get("active_queue") or "default").strip() or "default"
    queues = _QUEUE_CONTROL.get("queues")
    if not isinstance(queues, dict): queues = {}
    queues.setdefault("default", {"created_at": "", "updated_at": ""})
    queues.setdefault(active, {"created_at": "", "updated_at": ""})
    _QUEUE_CONTROL.update(active_queue=active, queues=queues)

def restore() -> None:
    path = Path(settings.UPDATE_RUNTIME_PATH)
    if not path.exists(): return
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return
    known = {item.name for item in fields(OperationalJob)}
    with _LOCK:
        for raw in payload.get("jobs", []):
            values = {key: value for key, value in raw.items() if key in known}
            try:
                values["state"] = JobState(values.get("state", "approved"))
                job = OperationalJob(**values)
            except (TypeError, ValueError):
                continue
            if job.state == JobState.EXECUTING:
                job.set_state(JobState.INTERRUPTED, "Execução interrompida; revalidação manual obrigatória")
            _JOBS[job.job_id] = job
        _PREVIEWS.update(payload.get("previews") or {})
        _PLANS.update(payload.get("plans") or {})
        _DISMISSED_HISTORY.update(payload.get("dismissed_history") or {})
        _QUEUE_CONTROL.update(payload.get("queue_control") or {})
        _normalize_queue_control()
        if _QUEUE_CONTROL.get("status") == "running":
            _QUEUE_CONTROL["status"] = "paused"
        migrated = False
        for job in _JOBS.values():
            migrated = _ensure_final_history(job) or migrated
            if job.state == JobState.QUEUED and not is_execution_eligible(
                job, _PREVIEWS.get(job.job_id), _PLANS.get(job.job_id)
            ):
                job.queue_position = 0
                job.execution_error = "Job removido da fila: pré-condições de execução não atendidas."
                job.set_state(JobState.BLOCKED, "Removido da fila por inelegibilidade")
                migrated = True
            if (job.state in {JobState.PREPARED, JobState.PLAN_READY}
                    and (_PREVIEWS.get(job.job_id) or {}).get("ready") is True):
                migrated = _archive_previous_execution(job) or migrated
        if migrated or (payload.get("queue_control") or {}).get("status") == "running":
            _persist()

def job_public(job: OperationalJob) -> dict[str, Any]:
    normalize_operational_job(job)
    preview = _PREVIEWS.get(job.job_id)
    plan = _PLANS.get(job.job_id)
    execution_eligible = is_execution_eligible(job, preview, plan)
    return {"job_id": job.job_id, "comparison_item_id": job.comparison_item_id,
            "woo_product_id": job.woo_product_id, "name": job.name,
            "plugintema_version": job.plugintema_version, "ultrapack_version": job.ultrapack_version,
            "approved_source_version": job.approved_source_version,
            "effective_source_version": job.effective_source_version,
            "ultrapack_url": job.ultrapack_url, "decision": job.decision,
            "relationship": job.relationship, "queue_type": job.queue_type,
            "state": job.state.value, "diagnostics": list(job.diagnostics),
            "prepared_at": job.prepared_at, "executing_at": job.executing_at,
            "completed_at": job.completed_at, "last_completed_step": job.last_completed_step,
            "execution_error": job.execution_error, "execution_logs": list(job.execution_logs),
            "version_write_evidence": dict(job.version_write_evidence),
            "execution_history": list(job.execution_history),
            "queue_position": job.queue_position, "queued_at": job.queued_at,
            "queue_name": getattr(job, "queue_name", "default"),
            "attempts": job.attempts, "canceled_at": job.canceled_at,
            "source_name": getattr(job, "source_name", ""),
            "initiated_by": getattr(job, "initiated_by", ""),
            "manual_requested_at": getattr(job, "manual_requested_at", ""),
            "cleanup_plan": build_cleanup_plan(job, plan),
            "execution_enabled": settings.UPDATE_EXECUTION_ENABLED,
            "execution_allowed_product_ids": sorted(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS),
            "execution_allow_all_products": not bool(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS),
            "execution_eligible": execution_eligible,
            "preview": preview, "execution_plan": plan,
            "queue_status": str(_QUEUE_CONTROL.get("status") or "stopped")}

def materialize(comparison_rows: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    queues = materialize_queue(comparison_rows=comparison_rows)
    with _LOCK:
        previous = {job.comparison_item_id: job for job in _JOBS.values()}
        for candidate in queues["update"]:
            dismissed_version = _DISMISSED_HISTORY.get(candidate.comparison_item_id)
            if dismissed_version == candidate.approved_source_version:
                continue
            if dismissed_version is not None:
                _DISMISSED_HISTORY.pop(candidate.comparison_item_id, None)
            old = previous.get(candidate.comparison_item_id)
            if old:
                normalize_operational_job(old)
                if old.state == JobState.EXECUTING:
                    _JOBS[old.job_id] = old
                    continue
                if old.state == JobState.COMPLETED:
                    _ensure_final_history(old)
                    installed = old.effective_source_version or old.plugintema_version
                    if not _is_newer_version(candidate.approved_source_version, installed):
                        if _is_newer_version(candidate.plugintema_version, old.plugintema_version):
                            old.plugintema_version = candidate.plugintema_version
                        _JOBS[old.job_id] = old
                        continue
                    candidate.execution_history = list(old.execution_history)
                    _JOBS.pop(old.job_id, None)
                    _JOBS[candidate.job_id] = candidate
                    continue
                candidate.job_id, candidate.state = old.job_id, old.state
                candidate.diagnostics = old.diagnostics
                candidate.effective_source_version = old.effective_source_version
                for key in ("prepared_at", "executing_at", "completed_at", "last_completed_step",
                            "current_sha256", "new_sha256", "local_staging_path",
                            "remote_staging_path", "backup_path", "execution_error", "execution_logs",
                            "version_write_evidence", "execution_history", "queue_position",
                            "queue_name", "queued_at", "attempts", "canceled_at"):
                    setattr(candidate, key, getattr(old, key, ""))
            _JOBS[candidate.job_id] = candidate
        _persist()
        return [job_public(job) for job in _JOBS.values() if job.queue_type == "update"]

def history_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [job_public(job) for job in _JOBS.values() if job.state in HISTORY_STATES]

def clear_update_history() -> dict[str, Any]:
    """Remove estados finais e impede que a mesma versão reapareça ao atualizar."""
    with _LOCK:
        job_ids = [job_id for job_id, job in _JOBS.items() if job.state in HISTORY_STATES]
        for job_id in job_ids:
            job = _JOBS.pop(job_id)
            _DISMISSED_HISTORY[job.comparison_item_id] = job.approved_source_version
            _PREVIEWS.pop(job_id, None)
            _PLANS.pop(job_id, None)
        _persist()
        return {"removed": len(job_ids), "queue": queue_snapshot()}

def get_job(job_id: str) -> OperationalJob:
    with _LOCK:
        if job_id not in _JOBS:
            raise KeyError("Job de atualização não encontrado")
        return normalize_operational_job(_JOBS[job_id])

def save_preview(job_id: str, preview: Mapping[str, Any]) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None and preview.get("ready") is True:
            _archive_previous_execution(job)
        _PREVIEWS[job_id] = dict(preview)
        # Novo PREPARAR invalida sempre qualquer plano anterior.
        _PLANS.pop(job_id, None)
        _persist()
        return _PREVIEWS[job_id]

def get_preview(job_id: str) -> dict[str, Any]:
    with _LOCK:
        if job_id not in _PREVIEWS:
            raise KeyError("Preview preparado não encontrado; prepare novamente")
        return dict(_PREVIEWS[job_id])

def save_plan(job_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    with _LOCK:
        _PLANS[job_id] = dict(plan)
        _persist()
        return _PLANS[job_id]

def clear_plan(job_id: str) -> None:
    with _LOCK:
        _PLANS.pop(job_id, None)
        _persist()

def persist_job(job: OperationalJob) -> None:
    with _LOCK:
        _JOBS[job.job_id] = job
        _persist()

def register_manual_job(job: OperationalJob) -> dict[str, Any]:
    """Registra um job externo na lista Manual sem trocar a fila ativa."""
    from app.operations.models import utc_now_iso
    with _LOCK:
        _normalize_queue_control()
        now = utc_now_iso()
        queues = _QUEUE_CONTROL["queues"]
        queues.setdefault("Manual", {"created_at": now, "updated_at": now})
        queues["Manual"]["updated_at"] = now
        last = max(
            (item.queue_position for item in _JOBS.values()
             if getattr(item, "queue_name", "") == "Manual"), default=0,
        )
        job.queue_name = "Manual"
        job.queue_position = last + 1
        job.queued_at = now
        _JOBS[job.job_id] = job
        _persist()
        return job_public(job)

def get_active_manual_job(product_id: int) -> OperationalJob | None:
    terminal = {JobState.COMPLETED, JobState.FAILED, JobState.ERROR, JobState.BLOCKED,
                JobState.ROLLED_BACK, JobState.ROLLBACK_REQUIRED, JobState.CANCELED,
                JobState.INTERRUPTED}
    with _LOCK:
        candidates = [
            normalize_operational_job(job) for job in _JOBS.values()
            if job.woo_product_id == int(product_id)
            and getattr(job, "queue_name", "") == "Manual" and job.state not in terminal
        ]
        return max(candidates, key=lambda item: item.created_at) if candidates else None

def queue_snapshot() -> dict[str, Any]:
    with _LOCK:
        _normalize_queue_control()
        active_queue = str(_QUEUE_CONTROL["active_queue"])
        queued = sorted(
            (job_public(job) for job in _JOBS.values() if job.state == JobState.QUEUED and getattr(job, "queue_name", "default") == active_queue),
            key=lambda item: (int(item.get("queue_position") or 0), item["queued_at"]),
        )
        executing = [job_public(job) for job in _JOBS.values() if job.state == JobState.EXECUTING and getattr(job, "queue_name", "default") == active_queue]
        return {"status": str(_QUEUE_CONTROL.get("status") or "stopped"),
                "active_queue": active_queue, "queues": list_update_queues(),
                "queued": queued, "executing": executing}

def list_update_queues() -> list[dict[str, Any]]:
    _normalize_queue_control()
    result = []
    for name, metadata in (_QUEUE_CONTROL.get("queues") or {}).items():
        jobs = [job for job in _JOBS.values() if getattr(job, "queue_name", "default") == name]
        completed = [job for job in jobs if job.state in {JobState.COMPLETED, JobState.ROLLED_BACK}]
        result.append({"name": name, "file": f"{_queue_slug(name)}.csv", "total": len(jobs), "completed": len(completed), "pending": len([job for job in jobs if job.state == JobState.QUEUED]), "last_completed_at": max((job.completed_at for job in completed), default=""), **dict(metadata or {})})
    return sorted(result, key=lambda item: item["name"].casefold())

def update_queue_details(name: str) -> dict[str, Any]:
    normalized = " ".join(str(name or "").split())
    with _LOCK:
        _normalize_queue_control()
        if normalized not in _QUEUE_CONTROL["queues"]:
            raise ValueError("Lista de atualização não encontrada.")
        items = []
        for job in sorted(
            (job for job in _JOBS.values() if getattr(job, "queue_name", "default") == normalized),
            key=lambda job: (job.queue_position or 10**9, job.updated_at, job.name.casefold()),
        ):
            items.append({
                "job_id": job.job_id, "position": job.queue_position,
                "woo_product_id": job.woo_product_id, "name": job.name,
                "state": job.state.value, "plugintema_version": job.plugintema_version,
                "source_version": job.effective_source_version or job.ultrapack_version,
                "queued_at": job.queued_at, "updated_at": job.updated_at,
                "completed_at": job.completed_at, "last_completed_step": job.last_completed_step,
                "execution_error": job.execution_error, "source": getattr(job, "source_name", ""),
                "previous_version": job.plugintema_version,
                "new_version": job.effective_source_version or job.approved_source_version,
                "requested_at": getattr(job, "manual_requested_at", ""),
                "result": job.execution_error or (job.diagnostics[-1] if job.diagnostics else ""),
            })
        metadata = next((item for item in list_update_queues() if item["name"] == normalized), {"name": normalized, "total": len(items)})
        return {"queue": metadata, "items": items}

def create_update_queue(name: str) -> dict[str, Any]:
    from app.operations.models import utc_now_iso
    normalized = " ".join(str(name or "").split())[:80]
    if not normalized: raise ValueError("Informe o nome da fila.")
    with _LOCK:
        _normalize_queue_control()
        queues = _QUEUE_CONTROL["queues"]
        if normalized in queues: raise ValueError("Já existe uma fila com esse nome.")
        now = utc_now_iso(); queues[normalized] = {"created_at": now, "updated_at": now}
        _QUEUE_CONTROL["active_queue"] = normalized
        _QUEUE_CONTROL["status"] = "stopped"
        _persist()
        return queue_snapshot()

def select_update_queue(name: str) -> dict[str, Any]:
    from app.operations.models import utc_now_iso
    normalized = " ".join(str(name or "").split())
    with _LOCK:
        _normalize_queue_control()
        if _QUEUE_CONTROL.get("status") == "running": raise ValueError("Pause a fila atual antes de trocar.")
        if normalized not in _QUEUE_CONTROL["queues"]: raise ValueError("Fila não encontrada.")
        _QUEUE_CONTROL.update(active_queue=normalized, status="paused" if any(job.state == JobState.QUEUED and getattr(job, "queue_name", "default") == normalized for job in _JOBS.values()) else "stopped", updated_at=utc_now_iso())
        _persist()
        return queue_snapshot()

def rename_update_queue(name: str, new_name: str) -> dict[str, Any]:
    from app.operations.models import utc_now_iso
    current = " ".join(str(name or "").split())
    renamed = " ".join(str(new_name or "").split())[:80]
    if not renamed: raise ValueError("Informe o novo nome da lista.")
    with _LOCK:
        _normalize_queue_control()
        if _QUEUE_CONTROL.get("status") == "running": raise ValueError("Pause a fila antes de renomear uma lista.")
        queues = _QUEUE_CONTROL["queues"]
        if current not in queues: raise ValueError("Lista de atualização não encontrada.")
        if current == "default": raise ValueError("A lista default não pode ser renomeada.")
        if renamed != current and renamed in queues: raise ValueError("Já existe uma lista com esse nome.")
        metadata = dict(queues.pop(current) or {})
        metadata["updated_at"] = utc_now_iso()
        queues[renamed] = metadata
        for job in _JOBS.values():
            if getattr(job, "queue_name", "default") == current: job.queue_name = renamed
        if _QUEUE_CONTROL.get("active_queue") == current: _QUEUE_CONTROL["active_queue"] = renamed
        old_file = Path(settings.UPDATE_QUEUES_DIR) / f"{_queue_slug(current)}.csv"
        if old_file.exists() and old_file.is_file(): old_file.unlink()
        _persist()
        return queue_snapshot()

def delete_update_queue(name: str) -> dict[str, Any]:
    from app.operations.models import utc_now_iso
    normalized = " ".join(str(name or "").split())
    with _LOCK:
        _normalize_queue_control()
        if _QUEUE_CONTROL.get("status") == "running": raise ValueError("Pause a fila antes de apagar uma lista.")
        if normalized == "default": raise ValueError("A lista default não pode ser apagada.")
        queues = _QUEUE_CONTROL["queues"]
        if normalized not in queues: raise ValueError("Lista de atualização não encontrada.")
        for job in _JOBS.values():
            if getattr(job, "queue_name", "default") != normalized: continue
            if job.state == JobState.QUEUED:
                job.canceled_at, job.queue_position = utc_now_iso(), 0
                job.set_state(JobState.CANCELED, "Lista de atualização apagada")
        queues.pop(normalized, None)
        if _QUEUE_CONTROL.get("active_queue") == normalized:
            _QUEUE_CONTROL.update(active_queue="default", status="stopped")
        target = Path(settings.UPDATE_QUEUES_DIR) / f"{_queue_slug(normalized)}.csv"
        if target.exists() and target.is_file(): target.unlink()
        _persist()
        return queue_snapshot()

def clear_update_queue(name: str) -> dict[str, Any]:
    """Esvazia uma lista sem apagar a lista nem o histórico dos jobs."""
    from app.operations.models import utc_now_iso
    normalized = " ".join(str(name or "").split())
    with _LOCK:
        _normalize_queue_control()
        if _QUEUE_CONTROL.get("status") == "running":
            raise ValueError("Pause a fila antes de limpar uma lista.")
        queues = _QUEUE_CONTROL["queues"]
        if normalized not in queues:
            raise ValueError("Lista de atualização não encontrada.")
        now = utc_now_iso()
        for job in _JOBS.values():
            if getattr(job, "queue_name", "default") != normalized:
                continue
            if job.state == JobState.QUEUED:
                job.canceled_at = now
                job.set_state(JobState.CANCELED, "Item removido ao limpar a lista de atualização")
            job.queue_name = ""
            job.queue_position = 0
            job.queued_at = ""
        metadata = dict(queues.get(normalized) or {})
        metadata.update(updated_at=now, cleared_at=now)
        queues[normalized] = metadata
        if _QUEUE_CONTROL.get("active_queue") == normalized:
            _QUEUE_CONTROL["status"] = "stopped"
        _persist()
        return queue_snapshot()

def enqueue_jobs(job_ids: Iterable[str]) -> list[dict[str, Any]]:
    from app.operations.models import utc_now_iso
    with _LOCK:
        _normalize_queue_control()
        active_queue = str(_QUEUE_CONTROL["active_queue"])
        last = max((job.queue_position for job in _JOBS.values() if getattr(job, "queue_name", "default") == active_queue), default=0)
        added: list[dict[str, Any]] = []
        for job_id in job_ids:
            job = _JOBS.get(str(job_id))
            if job is None or job.state != JobState.PLAN_READY:
                continue
            preview, plan = _PREVIEWS.get(job.job_id), _PLANS.get(job.job_id)
            if not is_execution_eligible(job, preview, plan):
                continue
            last += 1
            job.queue_name = active_queue
            job.queue_position, job.queued_at = last, utc_now_iso()
            job.set_state(JobState.QUEUED, "Adicionado à fila de atualização")
            added.append(job_public(job))
        _persist()
        return added

def set_queue_status(status: str) -> dict[str, Any]:
    from app.operations.models import utc_now_iso
    if status not in {"running", "paused", "stopped"}:
        raise ValueError("Estado de fila inválido")
    with _LOCK:
        _QUEUE_CONTROL.update(status=status, updated_at=utc_now_iso())
        _persist()
        return queue_snapshot()

def next_queued_job() -> OperationalJob | None:
    with _LOCK:
        if _QUEUE_CONTROL.get("status") != "running":
            return None
        active_queue = str(_QUEUE_CONTROL.get("active_queue") or "default")
        candidates = sorted((j for j in _JOBS.values() if j.state == JobState.QUEUED and getattr(j, "queue_name", "default") == active_queue),
                            key=lambda j: (j.queue_position, j.queued_at))
        return candidates[0] if candidates else None

def cancel_pending_queue() -> int:
    from app.operations.models import utc_now_iso
    with _LOCK:
        count = 0
        for job in _JOBS.values():
            if job.state == JobState.QUEUED and getattr(job, "queue_name", "default") == str(_QUEUE_CONTROL.get("active_queue") or "default"):
                job.canceled_at, job.queue_position = utc_now_iso(), 0
                job.set_state(JobState.CANCELED, "Cancelado antes do início da execução")
                count += 1
        _QUEUE_CONTROL["status"] = "stopped"
        _persist()
        return count

restore()

def get_plan(job_id: str) -> dict[str, Any]:
    with _LOCK:
        if job_id not in _PLANS:
            raise KeyError("Plano de execução não encontrado")
        return dict(_PLANS[job_id])
