from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MATERIALIZE: Callable[..., list[dict[str, Any]]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "active_processes.js"


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
        row = dict(raw)
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


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-active-processes>\n{script}\n</script>\n"
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
