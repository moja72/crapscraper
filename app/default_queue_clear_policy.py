from __future__ import annotations

from typing import Any

import app.operations.runtime as runtime
import app.web as web

_INSTALLED = False
_BASE_CLEAR = None


def _matches_queue(job: Any, name: str) -> bool:
    queue_name = str(getattr(job, "queue_name", "default") or "")
    if name == "default":
        # Compatibilidade com a limpeza antiga, que deixava os jobs órfãos com queue_name="".
        return queue_name in {"default", ""} and str(getattr(job, "queue_type", "")) == "update"
    return queue_name == name


def _purge_queue(name: str) -> dict[str, Any]:
    normalized = " ".join(str(name or "").split()) or "default"
    with runtime._LOCK:
        runtime._normalize_queue_control()
        if runtime._QUEUE_CONTROL.get("status") == "running":
            raise ValueError("Pause a fila antes de limpar uma lista.")
        queues = runtime._QUEUE_CONTROL.get("queues") or {}
        if normalized not in queues:
            raise ValueError("Lista de atualização não encontrada.")

        job_ids = [
            job_id for job_id, job in runtime._JOBS.items()
            if _matches_queue(job, normalized)
        ]
        for job_id in job_ids:
            job = runtime._JOBS.pop(job_id)
            comparison_item_id = str(getattr(job, "comparison_item_id", "") or "")
            approved_version = str(getattr(job, "approved_source_version", "") or "")
            if comparison_item_id and approved_version:
                # Evita que a mesma aprovação seja materializada novamente logo após a limpeza.
                runtime._DISMISSED_HISTORY[comparison_item_id] = approved_version
            runtime._PREVIEWS.pop(job_id, None)
            runtime._PLANS.pop(job_id, None)

        from app.operations.models import utc_now_iso
        now = utc_now_iso()
        metadata = dict(queues.get(normalized) or {})
        metadata.update(updated_at=now, cleared_at=now)
        queues[normalized] = metadata
        if runtime._QUEUE_CONTROL.get("active_queue") == normalized:
            runtime._QUEUE_CONTROL["status"] = "stopped"
        runtime._persist()
        return runtime.queue_snapshot()


def _migrate_previous_default_clear() -> None:
    """Conclui a limpeza antiga que deixou jobs aprovados com queue_name vazio."""
    with runtime._LOCK:
        runtime._normalize_queue_control()
        metadata = dict((runtime._QUEUE_CONTROL.get("queues") or {}).get("default") or {})
        if not metadata.get("cleared_at"):
            return
        has_orphans = any(
            str(getattr(job, "queue_name", "") or "") == ""
            and str(getattr(job, "queue_type", "")) == "update"
            for job in runtime._JOBS.values()
        )
    if has_orphans:
        _purge_queue("default")


def install_default_queue_clear_policy() -> None:
    global _INSTALLED, _BASE_CLEAR
    if _INSTALLED:
        return
    _BASE_CLEAR = runtime.clear_update_queue
    runtime.clear_update_queue = _purge_queue
    # app.web importou a função diretamente; atualiza também o binding usado pela rota HTTP.
    web.clear_update_queue = _purge_queue
    _migrate_previous_default_clear()
    _INSTALLED = True
