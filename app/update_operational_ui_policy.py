from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web
import app.operations.runtime as runtime

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MATERIALIZE: Callable[..., list[dict[str, Any]]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_operational_filters.js"


def _read_update_jobs(comparison_rows=()) -> list[dict[str, Any]]:
    """Leitura do painel não deve regravar runtime.json/CSVs a cada polling."""
    rows = tuple(comparison_rows or ())
    base = _BASE_MATERIALIZE or runtime.materialize
    if rows:
        return base(rows)

    with runtime._LOCK:
        return [
            runtime.job_public(job)
            for job in runtime._JOBS.values()
            if job.queue_type == "update"
        ]


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-update-operational-filters>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_update_operational_ui_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_MATERIALIZE
    if _INSTALLED:
        return
    _BASE_MATERIALIZE = web.materialize_update_jobs
    web.materialize_update_jobs = _read_update_jobs
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
