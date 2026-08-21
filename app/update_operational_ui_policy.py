from __future__ import annotations

import hashlib
import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from app import settings
from app.comparison_decisions import list_approved_updates
import app.web as web
import app.operations.runtime as runtime
from app.shared_environment_panel_policy import install_shared_environment_panel_policy

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MATERIALIZE: Callable[..., list[dict[str, Any]]] | None = None
_BASE_PREREQUISITES: Callable[..., dict[str, Any]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_operational_filters.js"
_CACHE_PATH = Path(settings.DATA_DIR) / "update_tab_cache.json"
_CACHE_LOCK = threading.RLock()
_PREREQUISITE_REFRESH_LOCK = threading.Lock()
_PREREQUISITE_TTL_SECONDS = 30.0

_MATERIALIZE_FIELDS = (
    "comparison_item_id",
    "woo_product_id",
    "site_id",
    "site_name",
    "source_name",
    "site_version",
    "source_version",
    "source_product_url",
    "source_official_url",
    "decision",
    "relationship_state",
    "queue_type",
)


def _load_cache_state() -> dict[str, Any]:
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


_CACHE_STATE: dict[str, Any] = _load_cache_state()


def _write_cache_state() -> None:
    with _CACHE_LOCK:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _CACHE_PATH.with_suffix(_CACHE_PATH.suffix + ".tmp")
        temporary.write_text(
            json.dumps(_CACHE_STATE, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(_CACHE_PATH)


def _update_cache_state(**values: Any) -> None:
    with _CACHE_LOCK:
        _CACHE_STATE.update(values)
        _write_cache_state()


def _current_update_jobs() -> list[dict[str, Any]]:
    with runtime._LOCK:
        return [
            runtime.job_public(job)
            for job in runtime._JOBS.values()
            if job.queue_type == "update"
        ]


def _regular_job_ids(jobs: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(job.get("job_id") or "")
        for job in jobs
        if str(job.get("job_id") or "")
        and str(job.get("queue_name") or "default") != "Manual"
    )


def _approved_update_signature(
    comparison_rows: tuple[Mapping[str, Any], ...],
) -> tuple[str, tuple[Mapping[str, Any], ...]]:
    approved = [
        dict(row)
        for row in list_approved_updates()
        if row.get("decision") == "approve_update" and row.get("queue_type") == "update"
    ]
    approved_ids = {
        str(row.get("comparison_item_id") or "")
        for row in approved
        if str(row.get("comparison_item_id") or "")
    }
    enrichment: dict[str, Mapping[str, Any]] = {}
    for row in comparison_rows:
        item_id = str(row.get("comparison_item_id") or "")
        if item_id and item_id in approved_ids:
            enrichment[item_id] = row

    canonical: list[dict[str, Any]] = []
    for decision in sorted(approved, key=lambda item: str(item.get("comparison_item_id") or "")):
        item_id = str(decision.get("comparison_item_id") or "")
        merged = dict(enrichment.get(item_id, {}))
        merged.update({key: value for key, value in decision.items() if value not in (None, "")})
        canonical.append({field: merged.get(field, "") for field in _MATERIALIZE_FIELDS})

    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    signature = hashlib.sha256(encoded).hexdigest()
    relevant_rows = tuple(enrichment[item_id] for item_id in sorted(enrichment))
    return signature, relevant_rows


def _materialize_cache_is_valid(signature: str, current_jobs: list[dict[str, Any]]) -> bool:
    with _CACHE_LOCK:
        cached_signature = str(_CACHE_STATE.get("materialize_signature") or "")
        cached_job_ids = sorted(str(item) for item in (_CACHE_STATE.get("materialize_job_ids") or []) if item)
    return bool(signature and signature == cached_signature and cached_job_ids == _regular_job_ids(current_jobs))


def _remember_materialization(signature: str, jobs: list[dict[str, Any]]) -> None:
    _update_cache_state(
        materialize_signature=signature,
        materialize_job_ids=_regular_job_ids(jobs),
        materialized_at=time.time(),
    )


def _read_update_jobs(comparison_rows=()) -> list[dict[str, Any]]:
    """Abre Atualizar usando runtime restaurado e só rematerializa quando a comparação mudou."""
    rows = tuple(comparison_rows or ())
    if not rows:
        return _current_update_jobs()

    signature, relevant_rows = _approved_update_signature(rows)
    current_jobs = _current_update_jobs()
    if _materialize_cache_is_valid(signature, current_jobs):
        return current_jobs

    base = _BASE_MATERIALIZE or runtime.materialize
    jobs = list(base(relevant_rows) or [])
    _remember_materialization(signature, jobs)
    return jobs


def _remember_prerequisites(result: Mapping[str, Any]) -> None:
    _update_cache_state(
        prerequisites=deepcopy(dict(result)),
        prerequisites_at=time.time(),
    )


def _refresh_prerequisites_in_background(app: Any) -> None:
    base = _BASE_PREREQUISITES
    if base is None or not _PREREQUISITE_REFRESH_LOCK.acquire(blocking=False):
        return

    def run() -> None:
        try:
            result = base(check_ssh_connection=False, app=app)
            if isinstance(result, Mapping):
                _remember_prerequisites(result)
        except Exception:
            pass
        finally:
            _PREREQUISITE_REFRESH_LOCK.release()

    threading.Thread(
        target=run,
        name="update-prerequisites-cache-refresh",
        daemon=True,
    ).start()


def _cached_update_prerequisites(*, check_ssh_connection: bool = False, app: Any = None) -> dict[str, Any]:
    """Serve o último diagnóstico imediatamente e revalida silenciosamente quando necessário."""
    base = _BASE_PREREQUISITES
    if base is None:
        return {}

    if check_ssh_connection:
        result = base(check_ssh_connection=True, app=app)
        if isinstance(result, Mapping):
            _remember_prerequisites(result)
        return dict(result or {})

    with _CACHE_LOCK:
        cached = deepcopy(_CACHE_STATE.get("prerequisites"))
        cached_at = float(_CACHE_STATE.get("prerequisites_at") or 0.0)

    if isinstance(cached, dict) and cached:
        if time.time() - cached_at >= _PREREQUISITE_TTL_SECONDS:
            _refresh_prerequisites_in_background(app)
        return cached

    result = base(check_ssh_connection=False, app=app)
    if isinstance(result, Mapping):
        _remember_prerequisites(result)
    return dict(result or {})


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
    global _INSTALLED, _BASE_RENDER, _BASE_MATERIALIZE, _BASE_PREREQUISITES
    if _INSTALLED:
        return

    _BASE_MATERIALIZE = web.materialize_update_jobs
    web.materialize_update_jobs = _read_update_jobs

    _BASE_PREREQUISITES = web._update_prerequisites
    web._update_prerequisites = _cached_update_prerequisites

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _INSTALLED = True
    install_shared_environment_panel_policy()
