from __future__ import annotations

from datetime import datetime
from typing import Any

from app.comparison_decisions import list_approved_updates
import app.operations.runtime as runtime
import app.web as web

_INSTALLED = False
_BASE_CLEAR = None
_BASE_MATERIALIZE = None


def _matches_queue(job: Any, name: str) -> bool:
    queue_name = str(getattr(job, "queue_name", "default") or "")
    if name == "default":
        # Compatibilidade com a limpeza antiga, que deixava os jobs órfãos com queue_name="".
        return queue_name in {"default", ""} and str(getattr(job, "queue_type", "")) == "update"
    return queue_name == name


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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
                # Impede a aprovação antiga de reaparecer imediatamente após a limpeza.
                # Uma nova aprovação posterior ao cleared_at libera o item novamente.
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


def _release_reapproved_items() -> int:
    """Libera versões reaprovadas depois da última limpeza da lista Padrão."""
    with runtime._LOCK:
        runtime._normalize_queue_control()
        metadata = dict((runtime._QUEUE_CONTROL.get("queues") or {}).get("default") or {})
        cleared_at = _parse_timestamp(metadata.get("cleared_at"))
        dismissed = dict(runtime._DISMISSED_HISTORY)

    if cleared_at is None or not dismissed:
        return 0

    approved = list_approved_updates()
    released: list[str] = []
    for row in approved:
        item_id = str(row.get("comparison_item_id") or "").strip()
        version = str(row.get("source_version") or "").strip()
        if not item_id or not version or dismissed.get(item_id) != version:
            continue
        updated_at = _parse_timestamp(row.get("updated_at"))
        if updated_at is not None and updated_at > cleared_at:
            released.append(item_id)

    if not released:
        return 0

    with runtime._LOCK:
        changed = 0
        for item_id in released:
            if item_id in runtime._DISMISSED_HISTORY:
                runtime._DISMISSED_HISTORY.pop(item_id, None)
                changed += 1
        if changed:
            runtime._persist()
        return changed


def _materialize(comparison_rows=()):
    _release_reapproved_items()
    return _BASE_MATERIALIZE(comparison_rows)


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
    global _INSTALLED, _BASE_CLEAR, _BASE_MATERIALIZE
    if _INSTALLED:
        return
    _BASE_CLEAR = runtime.clear_update_queue
    _BASE_MATERIALIZE = runtime.materialize
    runtime.clear_update_queue = _purge_queue
    runtime.materialize = _materialize
    # app.web importou as funções diretamente; atualiza também os bindings usados pelas rotas HTTP.
    web.clear_update_queue = _purge_queue
    web.materialize_update_jobs = _materialize
    _migrate_previous_default_clear()
    _INSTALLED = True
