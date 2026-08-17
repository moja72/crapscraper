from __future__ import annotations

from typing import Any

import app.operations.runtime as runtime
import app.web as web
from app.operations.models import JobState, utc_now_iso

_INSTALLED = False


def _reset_job(job: Any) -> None:
    """Volta o job ao estado operacional anterior a qualquer preparação/execução."""
    job.diagnostics = []
    job.effective_source_version = ""
    job.prepared_at = ""
    job.executing_at = ""
    job.completed_at = ""
    job.last_completed_step = ""
    job.current_sha256 = ""
    job.new_sha256 = ""
    job.local_staging_path = ""
    job.remote_staging_path = ""
    job.backup_path = ""
    job.execution_error = ""
    job.execution_logs = []
    job.version_write_evidence = {}
    job.execution_history = []
    job.queue_position = 0
    job.queue_name = ""
    job.queued_at = ""
    job.attempts = 0
    job.canceled_at = ""
    job.set_state(JobState.APPROVED)


def _reset_jobs(job_ids: list[str]) -> int:
    reset = 0
    for job_id in job_ids:
        job = runtime._JOBS.get(job_id)
        if job is None:
            continue
        _reset_job(job)
        runtime._PREVIEWS.pop(job_id, None)
        runtime._PLANS.pop(job_id, None)
        runtime._DISMISSED_HISTORY.pop(job.comparison_item_id, None)
        reset += 1
    return reset


def clear_update_history_reset() -> dict[str, Any]:
    """Limpa as duas abas de histórico e faz os itens voltarem a 'approved'."""
    with runtime._LOCK:
        if str(runtime._QUEUE_CONTROL.get("status") or "stopped") == "running":
            raise ValueError("Pause a fila antes de limpar o histórico.")
        job_ids = [
            job_id
            for job_id, job in runtime._JOBS.items()
            if job.state in runtime.HISTORY_STATES
        ]
        reset = _reset_jobs(job_ids)
        # O comportamento antigo marcava versões como dispensadas. Um reset real
        # precisa permitir que essas mesmas versões voltem ao fluxo.
        runtime._DISMISSED_HISTORY.clear()
        runtime._QUEUE_CONTROL["status"] = "stopped"
        runtime._QUEUE_CONTROL["updated_at"] = utc_now_iso()
        runtime._persist()
        return {"removed": reset, "reset": reset, "queue": runtime.queue_snapshot()}


def clear_update_queue_reset(name: str) -> dict[str, Any]:
    """Esvazia a lista e reseta todos os seus jobs como se nunca tivessem rodado."""
    normalized = " ".join(str(name or "").split())
    with runtime._LOCK:
        runtime._normalize_queue_control()
        if str(runtime._QUEUE_CONTROL.get("status") or "stopped") == "running":
            raise ValueError("Pause a fila antes de limpar uma lista.")
        queues = runtime._QUEUE_CONTROL.get("queues") or {}
        if normalized not in queues:
            raise ValueError("Lista de atualização não encontrada.")
        job_ids = [
            job_id
            for job_id, job in runtime._JOBS.items()
            if getattr(job, "queue_name", "default") == normalized
        ]
        if any(runtime._JOBS[job_id].state == JobState.EXECUTING for job_id in job_ids):
            raise ValueError("Há item em execução. Pause/aguarde a execução antes de limpar a fila.")
        reset = _reset_jobs(job_ids)
        now = utc_now_iso()
        metadata = dict(queues.get(normalized) or {})
        metadata.update(updated_at=now, cleared_at=now)
        queues[normalized] = metadata
        if runtime._QUEUE_CONTROL.get("active_queue") == normalized:
            runtime._QUEUE_CONTROL["status"] = "stopped"
        runtime._QUEUE_CONTROL["updated_at"] = now
        runtime._persist()
        snapshot = runtime.queue_snapshot()
        snapshot["reset"] = reset
        return snapshot


def install_update_reset_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    # app.web importou as funções de runtime por nome; substituímos os aliases
    # usados pelas rotas existentes sem criar endpoints paralelos.
    runtime.clear_update_history = clear_update_history_reset
    runtime.clear_update_queue = clear_update_queue_reset
    web.clear_update_history = clear_update_history_reset
    web.clear_update_queue = clear_update_queue_reset
    _INSTALLED = True
