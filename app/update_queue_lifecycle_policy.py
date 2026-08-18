from __future__ import annotations

from typing import Any, Callable, Mapping

import app.operations.runtime as runtime
import app.web as web
from app.operations.models import JobState

_INSTALLED = False
_BASE_SAVE_PLAN: Callable[[str, Mapping[str, Any]], dict[str, Any]] | None = None


def _attach_plan_ready_job_to_active_queue(job_id: str) -> None:
    """Faz o job preparado pertencer de verdade à lista de atualização ativa."""
    with runtime._LOCK:
        runtime._normalize_queue_control()
        job = runtime._JOBS.get(str(job_id))
        if job is None or job.state != JobState.PLAN_READY:
            return
        if str(getattr(job, "queue_type", "") or "") != "update":
            return
        if str(getattr(job, "queue_name", "") or "") == "Manual":
            return

        active_queue = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        job.queue_name = active_queue
        runtime._persist()


def _save_plan(job_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    if _BASE_SAVE_PLAN is None:
        raise RuntimeError("save_plan base indisponível")
    saved = _BASE_SAVE_PLAN(job_id, plan)
    if bool(saved.get("ready")):
        _attach_plan_ready_job_to_active_queue(job_id)
    return saved


def install_update_queue_lifecycle_policy() -> None:
    global _INSTALLED, _BASE_SAVE_PLAN
    if _INSTALLED:
        return

    _BASE_SAVE_PLAN = runtime.save_plan
    runtime.save_plan = _save_plan
    # app.web importou save_plan diretamente; a rota /atualizacoes/plano usa este binding.
    web.save_plan = _save_plan
    _INSTALLED = True
