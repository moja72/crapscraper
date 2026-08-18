from __future__ import annotations

from typing import Any, Callable, Mapping

import app.operations.runtime as runtime
import app.web as web
from app.operations.models import JobState

_INSTALLED = False
_BASE_SAVE_PLAN: Callable[[str, Mapping[str, Any]], dict[str, Any]] | None = None


def _eligible_ready_job_ids() -> list[str]:
    """Lista jobs prontos da fila ativa que já podem virar itens aguardando execução."""
    with runtime._LOCK:
        runtime._normalize_queue_control()
        active_queue = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        return [
            str(job.job_id)
            for job in runtime._JOBS.values()
            if job.state == JobState.PLAN_READY
            and str(getattr(job, "queue_type", "") or "") == "update"
            and str(getattr(job, "queue_name", "default") or "default") != "Manual"
            and str(getattr(job, "queue_name", "default") or "default") in {"", active_queue, "default"}
            and runtime.is_execution_eligible(
                job,
                runtime._PREVIEWS.get(job.job_id),
                runtime._PLANS.get(job.job_id),
            )
        ]


def _attach_plan_ready_job_to_active_queue(job_id: str) -> bool:
    """Faz o job preparado pertencer de verdade à lista de atualização ativa."""
    with runtime._LOCK:
        runtime._normalize_queue_control()
        job = runtime._JOBS.get(str(job_id))
        if job is None or job.state != JobState.PLAN_READY:
            return False
        if str(getattr(job, "queue_type", "") or "") != "update":
            return False
        if str(getattr(job, "queue_name", "") or "") == "Manual":
            return False

        active_queue = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        job.queue_name = active_queue
        runtime._persist()
        return True


def _enqueue_plan_ready_job(job_id: str) -> list[dict[str, Any]]:
    """Transforma Plano pronto em Aguardando execução sem iniciar escrita sozinho."""
    if not _attach_plan_ready_job_to_active_queue(job_id):
        return []
    return runtime.enqueue_jobs([job_id])


def _resume_worker_if_queue_is_running(added: list[dict[str, Any]]) -> None:
    """Se a fila já estava rodando, um plano recém-pronto não pode ficar órfão."""
    if not added:
        return
    snapshot = runtime.queue_snapshot()
    if str(snapshot.get("status") or "") == "running":
        web._start_update_queue_worker()


def _save_plan(job_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    if _BASE_SAVE_PLAN is None:
        raise RuntimeError("save_plan base indisponível")
    saved = _BASE_SAVE_PLAN(job_id, plan)
    if bool(saved.get("ready")):
        added = _enqueue_plan_ready_job(job_id)
        _resume_worker_if_queue_is_running(added)
    return saved


def _migrate_existing_ready_jobs() -> None:
    """Corrige jobs que já estavam em Plano pronto antes desta política ser instalada."""
    for job_id in _eligible_ready_job_ids():
        _enqueue_plan_ready_job(job_id)


def install_update_queue_lifecycle_policy() -> None:
    global _INSTALLED, _BASE_SAVE_PLAN
    if _INSTALLED:
        return

    _BASE_SAVE_PLAN = runtime.save_plan
    runtime.save_plan = _save_plan
    # app.web importou save_plan diretamente; a rota /atualizacoes/plano usa este binding.
    web.save_plan = _save_plan
    _INSTALLED = True

    # O restore do runtime ocorre antes das políticas. Portanto corrigimos também
    # planos prontos persistidos de sessões anteriores: eles entram como queued,
    # mas a execução continua exigindo o botão "Executar fila" quando a fila está parada.
    _migrate_existing_ready_jobs()
