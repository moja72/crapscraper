from __future__ import annotations

import math
from typing import Any

from app.updates.service import UpdateService


_INSTALLED = False
_ORIGINAL_LIST = None
_ORIGINAL_JOB = None
_ORIGINAL_SELECTION = None


def _batch_roles(service: UpdateService) -> tuple[str, set[str]]:
    """Return (current_job_id, queued_job_ids) from the in-memory batch."""
    batch = service.batch
    try:
        with batch.lock:
            alive = bool(batch.thread and batch.thread.is_alive())
            cancelled = bool(batch.cancelled)
            ids = list(batch.ids)
            position = int(batch.position)
            processed = len(batch.results)
    except Exception:
        return "", set()

    if not alive or cancelled or not ids:
        return "", set()

    current = ""
    if position > processed and 0 < position <= len(ids):
        current = str(ids[position - 1])
    queued = {str(job_id) for job_id in ids[position:]}
    queued.discard(current)
    return current, queued


def _project_job(service: UpdateService, job: dict[str, Any]) -> dict[str, Any]:
    item = dict(job)
    current, queued = _batch_roles(service)
    job_id = str(item.get("job_id") or "")
    state = str(item.get("state") or "")

    if job_id in queued and state in {"ready", "error"}:
        item["state"] = "queued"
        item["group"] = "queued"
        item["stage"] = "queued"
        item["execution"] = {
            "allowed": False,
            "action": "none",
            "blockers": [
                {
                    "code": "job_queued",
                    "message": "Produto já está na fila e aguarda sua vez para iniciar.",
                }
            ],
        }
        progress = dict(item.get("progress") or {})
        progress.update(
            active=False,
            complete=False,
            failed=False,
            stage="queued",
            label="Na fila",
        )
        item["progress"] = progress
        return item

    # Existe uma janela curta entre o worker retirar o primeiro ID da fila e o
    # repository.begin_attempt gravar public_state=running. Projete essa janela
    # como Em andamento para a UI nunca voltar visualmente a Preparados.
    if job_id == current and state in {"ready", "error"}:
        item["state"] = "running"
        item["group"] = "running"
        item["stage"] = "starting"
        item["execution"] = {
            "allowed": False,
            "action": "none",
            "blockers": [
                {"code": "job_starting", "message": "Produto está iniciando a execução."}
            ],
        }
        progress = dict(item.get("progress") or {})
        progress.update(active=True, complete=False, failed=False, stage="starting", label="Iniciando execução")
        item["progress"] = progress
    return item


def _all_repository_items(
    service: UpdateService,
    *,
    query: str = "",
    stage: str = "",
    sort_by: str = "date",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    first = service.repository.list(
        query=query,
        group="",
        stage=stage,
        page=1,
        page_size=100,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    items = list(first["items"])
    for page in range(2, int(first.get("pages") or 1) + 1):
        items.extend(
            service.repository.list(
                query=query,
                group="",
                stage=stage,
                page=page,
                page_size=100,
                sort_by=sort_by,
                sort_order=sort_order,
            )["items"]
        )
    return [service._with_execution(item) for item in items]


def _counts(service: UpdateService) -> dict[str, int]:
    items = [_project_job(service, item) for item in _all_repository_items(service)]
    counts = {"total": len(items), "prepared": 0, "queued": 0, "running": 0, "success": 0, "error": 0}
    for item in items:
        group = str(item.get("group") or "")
        if group in counts:
            counts[group] += 1
    return counts


def _list(self: UpdateService, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    p = payload or {}
    query = str(p.get("query") or "")
    group = str(p.get("group") or "")
    stage = str(p.get("stage") or "")
    sort_by = str(p.get("sort_by") or "date")
    sort_order = str(p.get("sort_order") or "desc")
    page = max(1, int(p.get("page") or 1))
    page_size = max(1, min(100, int(p.get("page_size") or 5)))

    if group not in {"", "prepared", "queued", "running", "success", "error"}:
        raise ValueError("Grupo operacional inválido")

    items = [
        _project_job(self, item)
        for item in _all_repository_items(
            self,
            query=query,
            stage=stage,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    ]
    if group:
        items = [item for item in items if str(item.get("group") or "") == group]

    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    page = min(page, pages)
    start = (page - 1) * page_size
    visible = items[start : start + page_size]

    return {
        "ok": True,
        "items": visible,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "counts": _counts(self),
        "sort_by": sort_by,
        "sort_order": sort_order,
        "batch": self.batch.state(),
        "database": str(self.repository.path),
    }


def _job(self: UpdateService, job_id: str) -> dict[str, Any]:
    job = self._with_execution(self.repository.get(job_id))
    return {
        "ok": True,
        "item": _project_job(self, job),
        "history": self.repository.history(job_id),
    }


def _selection(self: UpdateService, payload: dict[str, Any]) -> dict[str, Any]:
    request = dict(payload or {})
    request["page"] = 1
    request["page_size"] = 100
    first = _list(self, request)
    items = list(first["items"])
    for page in range(2, int(first["pages"]) + 1):
        request["page"] = page
        items.extend(_list(self, request)["items"])
    return {"ok": True, "items": items, "total": len(items)}


def install_update_queue_state_runtime() -> None:
    global _INSTALLED, _ORIGINAL_LIST, _ORIGINAL_JOB, _ORIGINAL_SELECTION
    if _INSTALLED:
        return
    _ORIGINAL_LIST = UpdateService.list
    _ORIGINAL_JOB = UpdateService.job
    _ORIGINAL_SELECTION = UpdateService.selection
    UpdateService.list = _list
    UpdateService.job = _job
    UpdateService.selection = _selection
    _INSTALLED = True


__all__ = [
    "install_update_queue_state_runtime",
    "_batch_roles",
    "_project_job",
]
