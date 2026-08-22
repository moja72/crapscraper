from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import app.addition_operational_ui_policy as addition_operational
import app.new_product_workflow_policy as additions
import app.operations.runtime as update_runtime
import app.web as web
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_SERVER: Any = None
_BASE_HISTORY_PAGE: Callable[..., dict[str, Any]] | None = None
_BASE_HISTORY_CSV: Callable[..., bytes] | None = None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backfill_completed_addition_history() -> int:
    """Materializa no histórico conclusões antigas que antecedem o registro por tentativa.

    Alguns produtos já concluídos existem em ``addition_jobs`` sem uma linha em
    ``addition_attempt_history``. O resumo usa ``addition_jobs`` e por isso exibia
    Concluídos (N), enquanto a listagem do Histórico retornava zero registros.
    """

    addition_operational._ensure_schema()
    inserted = 0
    now = _utc_now()
    with additions._db() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT j.*
                FROM addition_jobs j
                WHERE (j.queue_state='completed' OR j.state='completed')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM addition_attempt_history h
                      WHERE h.job_id=j.job_id AND h.status='completed'
                  )
                ORDER BY j.updated_at, j.created_at
                """
            ).fetchall()
        ]
        for row in rows:
            job_id = _clean(row.get("job_id"))
            previous = connection.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) AS attempt_no "
                "FROM addition_attempt_history WHERE job_id=?",
                (job_id,),
            ).fetchone()
            previous_no = _safe_int(previous["attempt_no"] if previous else 0)
            attempt_no = max(1, _safe_int(row.get("attempts")), previous_no + 1)
            started_at = (
                _clean(row.get("started_at"))
                or _clean(row.get("created_at"))
                or _clean(row.get("updated_at"))
                or now
            )
            finished_at = (
                _clean(row.get("finished_at"))
                or _clean(row.get("updated_at"))
                or started_at
            )
            logs = addition_operational._dump_logs(
                addition_operational._load_logs(row.get("execution_logs"))
            )
            connection.execute(
                """
                INSERT INTO addition_attempt_history (
                    job_id, attempt_no, status, result, final_state, current_step,
                    progress, error, logs, source_name, source_version,
                    source_product_url, source_official_url, desenvolvedor,
                    site_oficial, kind, category_name, woo_product_id,
                    started_at, finished_at
                ) VALUES (?, ?, 'completed', 'Concluído', 'completed', 'completed',
                          100, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    attempt_no,
                    logs,
                    _clean(row.get("source_name")) or _clean(row.get("title")),
                    _clean(row.get("source_version")),
                    _clean(row.get("source_product_url")),
                    _clean(row.get("source_official_url")),
                    _clean(row.get("desenvolvedor")),
                    _clean(row.get("site_oficial")),
                    _clean(row.get("kind")),
                    _clean(row.get("category_name")),
                    _safe_int(row.get("woo_product_id")),
                    started_at,
                    finished_at,
                ),
            )
            if _safe_int(row.get("attempts")) < attempt_no:
                connection.execute(
                    "UPDATE addition_jobs SET attempts=? WHERE job_id=?",
                    (attempt_no, job_id),
                )
            inserted += 1
    return inserted


def _addition_completion_rows() -> list[dict[str, Any]]:
    _backfill_completed_addition_history()
    with additions._db() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT job_id, comparison_item_id, woo_product_id, source_name,
                       source_version, finished_at, updated_at
                FROM addition_jobs
                WHERE queue_state='completed' OR state='completed'
                ORDER BY COALESCE(NULLIF(finished_at,''), updated_at) DESC
                """
            ).fetchall()
        ]
    return [
        {
            "kind": "addition",
            "label": "Já adicionado",
            "job_id": _clean(row.get("job_id")),
            "comparison_item_id": _clean(row.get("comparison_item_id")),
            "woo_product_id": _safe_int(row.get("woo_product_id")),
            "name": _clean(row.get("source_name")),
            "version": _clean(row.get("source_version")),
            "completed_at": _clean(row.get("finished_at")) or _clean(row.get("updated_at")),
        }
        for row in rows
    ]


def _successful_update_history(job: dict[str, Any]) -> dict[str, Any] | None:
    state = _clean(job.get("state"))
    if state == "completed":
        return {
            "completed_at": _clean(job.get("completed_at")),
            "version": _clean(job.get("effective_source_version")) or _clean(job.get("approved_source_version")),
        }
    history = job.get("execution_history")
    if not isinstance(history, list):
        return None
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        completed_at = _clean(entry.get("completed_at"))
        error = _clean(entry.get("error"))
        evidence = entry.get("version_write_evidence")
        if completed_at and not error and (evidence or _clean(entry.get("last_completed_step"))):
            return {
                "completed_at": completed_at,
                "version": _clean(job.get("plugintema_version")) or _clean(job.get("effective_source_version")),
            }
    return None


def _update_completion_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_comparison: set[str] = set()
    try:
        with update_runtime._LOCK:
            jobs = [
                update_runtime.job_public(job)
                for job in update_runtime._JOBS.values()
                if getattr(job, "queue_type", "") == "update"
            ]
            dismissed = dict(update_runtime._DISMISSED_HISTORY)
    except Exception:
        jobs = list(update_runtime.history_jobs())
        dismissed = {}

    for job in jobs:
        success = _successful_update_history(job)
        if success is None:
            continue
        comparison_item_id = _clean(job.get("comparison_item_id"))
        if comparison_item_id:
            seen_comparison.add(comparison_item_id)
        rows.append(
            {
                "kind": "update",
                "label": "Já atualizado",
                "job_id": _clean(job.get("job_id")),
                "comparison_item_id": comparison_item_id,
                "woo_product_id": _safe_int(job.get("woo_product_id")),
                "name": _clean(job.get("name")) or _clean(job.get("source_name")),
                "version": _clean(success.get("version")),
                "completed_at": _clean(success.get("completed_at")),
            }
        )

    # Quando o usuário limpa o Histórico de Atualizações, runtime conserva a
    # versão concluída em _DISMISSED_HISTORY para que a mesma versão não volte.
    # Mantemos essa informação visível na Comparação mesmo após limpar o painel.
    for comparison_item_id, version in dismissed.items():
        key = _clean(comparison_item_id)
        if not key or key in seen_comparison:
            continue
        rows.append(
            {
                "kind": "update",
                "label": "Já atualizado",
                "job_id": "",
                "comparison_item_id": key,
                "woo_product_id": 0,
                "name": "",
                "version": _clean(version),
                "completed_at": "",
            }
        )
    return rows


def _completion_snapshot() -> dict[str, Any]:
    return {
        "ok": True,
        "additions": _addition_completion_rows(),
        "updates": _update_completion_rows(),
    }


def _history_page_reconciled(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _backfill_completed_addition_history()
    base = _BASE_HISTORY_PAGE or addition_operational._history_page
    return base(*args, **kwargs)


def _history_csv_reconciled(*args: Any, **kwargs: Any) -> bytes:
    _backfill_completed_addition_history()
    base = _BASE_HISTORY_CSV or addition_operational._history_csv
    return base(*args, **kwargs)


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class OperationCompletionHandler(handler_class):
        def do_GET(self) -> None:
            if self._request_path() == "/operacoes/conclusoes":
                try:
                    self._send_json(_completion_snapshot())
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_GET()

    return _BASE_SERVER(server_address, OperationCompletionHandler, *args, **kwargs)


def install_operation_completion_visibility_policy() -> None:
    global _INSTALLED, _BASE_SERVER, _BASE_HISTORY_PAGE, _BASE_HISTORY_CSV
    if _INSTALLED:
        return

    _backfill_completed_addition_history()

    _BASE_HISTORY_PAGE = addition_operational._history_page
    addition_operational._history_page = _history_page_reconciled
    _BASE_HISTORY_CSV = addition_operational._history_csv
    addition_operational._history_csv = _history_csv_reconciled

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
