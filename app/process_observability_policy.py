from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import app.operations.runtime as runtime
import app.web as web
from app.operations.models import JobState, utc_now_iso

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MATERIALIZE: Callable[..., list[dict[str, Any]]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "active_processes.js"
_STATE_SYNC_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_state_sync.js"
_SUCCESS_RESULTS = frozenset({"completed", "already_current"})
_SUCCESS_STEPS = frozenset({"pt_versao_updated", "already_current"})


def _matching_success_history(job: Mapping[str, Any]) -> bool:
    completed_at = str(job.get("completed_at") or "").strip()
    executing_at = str(job.get("executing_at") or "").strip()
    if not completed_at or str(job.get("execution_error") or "").strip():
        return False
    if str(job.get("last_completed_step") or "").strip() not in _SUCCESS_STEPS:
        return False
    history = [item for item in job.get("execution_history", []) or [] if isinstance(item, Mapping)]
    for item in reversed(history):
        if str(item.get("result") or "").strip() not in _SUCCESS_RESULTS:
            continue
        if completed_at and str(item.get("completed_at") or "").strip() == completed_at:
            return True
        if executing_at and str(item.get("executing_at") or "").strip() == executing_at:
            return True
    return False


def _repair_successful_terminal_state(row: Mapping[str, Any]) -> dict[str, Any]:
    """Evita estado terminal contraditório após uma execução comprovadamente concluída.

    O reparo só ocorre com evidências persistidas do ciclo atual: completed_at, ausência de
    execution_error, última etapa de sucesso e execution_history correspondente. Logs, sozinhos,
    nunca são usados para promover um job a concluído.
    """
    current = dict(row)
    if str(current.get("state") or "") == JobState.COMPLETED.value:
        return current
    if not _matching_success_history(current):
        return current

    job_id = str(current.get("job_id") or "").strip()
    if not job_id:
        return current
    with runtime._LOCK:
        job = runtime._JOBS.get(job_id)
        if job is None:
            return current
        public = runtime.job_public(job)
        if not _matching_success_history(public):
            return current
        if job.state != JobState.COMPLETED:
            job.state = JobState.COMPLETED
            job.updated_at = utc_now_iso()
            job.execution_error = ""
            marker = "Estado reconciliado para Concluído a partir das evidências persistidas da execução."
            if not job.diagnostics or job.diagnostics[-1] != marker:
                job.diagnostics.append(marker)
            runtime._ensure_final_history(job)
            runtime._persist()
        return runtime.job_public(job)


def _current_history_ready(job: Mapping[str, Any]) -> bool:
    """Confirma se o ciclo final atual já possui evidência no histórico do job."""
    state = str(job.get("state") or "")
    if state not in {"completed", "rolled_back"}:
        return False
    history = [item for item in job.get("execution_history", []) or [] if isinstance(item, Mapping)]
    if not history:
        return False
    completed_at = str(job.get("completed_at") or "")
    executing_at = str(job.get("executing_at") or "")
    if completed_at:
        return any(str(item.get("completed_at") or "") == completed_at for item in history)
    if executing_at:
        return any(str(item.get("executing_at") or "") == executing_at for item in history)
    return True


def _patched_materialize_update_jobs(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    base = _BASE_MATERIALIZE or web.materialize_update_jobs
    rows = base(*args, **kwargs)
    enriched: list[dict[str, Any]] = []
    for raw in rows:
        row = _repair_successful_terminal_state(raw)
        job_id = str(row.get("job_id") or "").strip()
        live_logs: list[str] = []
        if job_id:
            try:
                live_logs = list(web._UPDATE_LOGS.to_list(job_id))
            except Exception:
                live_logs = []
        persisted_logs = [str(item) for item in row.get("execution_logs", []) or []]
        visible_logs = live_logs or persisted_logs
        row["live_execution_logs"] = live_logs
        row["live_log_tail"] = visible_logs[-1] if visible_logs else ""
        row["live_log_count"] = len(visible_logs)
        row["history_ready"] = _current_history_ready(row)
        enriched.append(row)
    return enriched


def _script_block(path: Path, attribute: str) -> str:
    try:
        script = path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script {attribute}>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = (
        _script_block(_SCRIPT_PATH, "data-active-processes")
        + _script_block(_STATE_SYNC_SCRIPT_PATH, "data-update-state-sync")
    )
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_process_observability_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_MATERIALIZE
    if _INSTALLED:
        return
    _BASE_MATERIALIZE = web.materialize_update_jobs
    web.materialize_update_jobs = _patched_materialize_update_jobs
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
