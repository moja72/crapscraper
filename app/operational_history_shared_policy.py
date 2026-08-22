from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

import app.addition_operational_ui_policy as addition_ui
import app.new_product_workflow_policy as additions
import app.operational_reliability_policy as reliability
import app.operations.runtime as update_runtime
import app.web as web
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_SERVER: Any = None

_COMPLETED_STATES = {"completed", "rolled_back"}
_ERROR_STATES = {"error", "failed", "blocked", "rollback_required", "interrupted", "canceled"}

_STATUS_LABELS = {
    "running": "Em andamento",
    "completed": "Concluído",
    "rolled_back": "Rollback concluído",
    "error": "Erro",
    "failed": "Falhou",
    "blocked": "Bloqueado",
    "rollback_required": "Rollback necessário",
    "interrupted": "Interrompido",
    "canceled": "Cancelado",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _bucket(status: str) -> str:
    if status in _COMPLETED_STATES:
        return "completed"
    if status in _ERROR_STATES:
        return "errors"
    return "other"


def _duration_seconds(started_at: str, finished_at: str) -> int:
    if not started_at or not finished_at:
        return 0
    try:
        left = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        right = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    try:
        return max(0, int((right - left).total_seconds()))
    except TypeError:
        return 0


def _update_origin(row: Mapping[str, Any]) -> str:
    explicit = _clean(row.get("source_name"))
    if explicit:
        return explicit
    url = _clean(row.get("ultrapack_url"))
    return addition_ui._origin_label(url) if url else "Origem não identificada"


def _addition_rows() -> list[dict[str, Any]]:
    reliability._backfill_terminal_addition_history()
    addition_ui._ensure_schema()
    with additions._db() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM addition_attempt_history ORDER BY attempt_id DESC LIMIT 10000"
            ).fetchall()
        ]

    result: list[dict[str, Any]] = []
    for row in rows:
        status = _clean(row.get("status")) or _clean(row.get("final_state")) or "completed"
        started_at = _clean(row.get("started_at"))
        finished_at = _clean(row.get("finished_at"))
        source_url = _clean(row.get("source_product_url"))
        result.append(
            {
                "kind": "addition",
                "job_id": _clean(row.get("job_id")),
                "name": _clean(row.get("source_name")) or _clean(row.get("job_id")),
                "woo_product_id": _safe_int(row.get("woo_product_id")),
                "attempt_no": _safe_int(row.get("attempt_no")),
                "status": status,
                "status_label": _STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
                "bucket": _bucket(status),
                "result": _clean(row.get("result")),
                "origin": addition_ui._origin_label(source_url),
                "source_url": source_url,
                "official_url": _clean(row.get("site_oficial")) or _clean(row.get("source_official_url")),
                "developer": _clean(row.get("desenvolvedor")),
                "category": _clean(row.get("category_name")),
                "product_type": "Tema" if _clean(row.get("kind")) == "theme" else "Plugin",
                "version_from": "",
                "version_to": _clean(row.get("source_version")),
                "started_at": started_at,
                "finished_at": finished_at,
                "date": finished_at or started_at,
                "duration_seconds": _duration_seconds(started_at, finished_at),
                "current_step": _clean(row.get("current_step")),
                "progress": max(0, min(100, _safe_int(row.get("progress")))),
                "final_state": _clean(row.get("final_state")) or status,
                "error": _clean(row.get("error")),
                "logs": addition_ui._load_logs(row.get("logs")),
            }
        )
    return result


def _update_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with update_runtime._LOCK:
        jobs = [
            job
            for job in update_runtime._JOBS.values()
            if getattr(job, "queue_type", "") == "update" and job.state in update_runtime.HISTORY_STATES
        ]
        public_rows = [
            (
                update_runtime.job_public(job),
                _clean(getattr(job, "created_at", "")),
                _clean(getattr(job, "updated_at", "")),
            )
            for job in jobs
        ]

    for row, created_at, updated_at in public_rows:
        status = _clean(row.get("state"))
        started_at = (
            _clean(row.get("executing_at"))
            or _clean(row.get("manual_requested_at"))
            or _clean(row.get("queued_at"))
            or created_at
        )
        finished_at = (
            _clean(row.get("completed_at"))
            or _clean(row.get("canceled_at"))
            or updated_at
            or started_at
        )
        logs = row.get("execution_logs") if isinstance(row.get("execution_logs"), list) else []
        error = _clean(row.get("execution_error"))
        result_text = error or _STATUS_LABELS.get(status, status.replace("_", " ").capitalize())
        rows.append(
            {
                "kind": "update",
                "job_id": _clean(row.get("job_id")),
                "name": _clean(row.get("name")) or _clean(row.get("source_name")) or _clean(row.get("job_id")),
                "woo_product_id": _safe_int(row.get("woo_product_id")),
                "attempt_no": max(0, _safe_int(row.get("attempts"))),
                "status": status,
                "status_label": _STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
                "bucket": _bucket(status),
                "result": result_text,
                "origin": _update_origin(row),
                "source_url": _clean(row.get("ultrapack_url")),
                "official_url": "",
                "developer": "",
                "category": "",
                "product_type": "Atualização",
                "version_from": _clean(row.get("plugintema_version")),
                "version_to": (
                    _clean(row.get("effective_source_version"))
                    or _clean(row.get("approved_source_version"))
                    or _clean(row.get("ultrapack_version"))
                ),
                "started_at": started_at,
                "finished_at": finished_at,
                "date": finished_at or started_at,
                "duration_seconds": _duration_seconds(started_at, finished_at),
                "current_step": _clean(row.get("last_completed_step")),
                "progress": 100 if status in _COMPLETED_STATES else 0,
                "final_state": status,
                "error": error,
                "logs": [str(item) for item in logs if str(item or "").strip()][-20:],
            }
        )
    rows.sort(key=lambda item: item.get("date") or "", reverse=True)
    return rows


def _snapshot(kind: str) -> dict[str, Any]:
    normalized = _clean(kind).lower()
    if normalized == "addition":
        items = _addition_rows()
    elif normalized == "update":
        items = _update_rows()
    else:
        raise ValueError("Tipo de histórico inválido.")

    completed = sum(1 for item in items if item.get("bucket") == "completed")
    errors = sum(1 for item in items if item.get("bucket") == "errors")
    return {
        "ok": True,
        "kind": normalized,
        "items": items,
        "total": len(items),
        "counts": {"completed": completed, "errors": errors},
    }


def _clear(kind: str) -> dict[str, Any]:
    normalized = _clean(kind).lower()
    if normalized == "addition":
        addition_ui._ensure_schema()
        with additions._db() as connection:
            cursor = connection.execute("DELETE FROM addition_attempt_history")
            removed = max(0, cursor.rowcount)
        return {"ok": True, "removed": removed, "message": f"{removed} registro(s) removido(s) do histórico de adições."}
    if normalized == "update":
        result = update_runtime.clear_update_history()
        return {"ok": True, **result, "message": f"{_safe_int(result.get('removed'))} registro(s) removido(s) do histórico de atualizações."}
    raise ValueError("Tipo de histórico inválido.")


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class SharedOperationalHistoryHandler(handler_class):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/operacoes/historico":
                try:
                    query = parse_qs(parsed.query or "")
                    kind = str((query.get("kind") or [""])[0] or "")
                    self._send_json(_snapshot(kind))
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            if self._request_path() != "/operacoes/historico/apagar":
                return super().do_POST()
            try:
                payload = self._read_json_body()
                self._send_json(_clear(str(payload.get("kind") or "")))
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, SharedOperationalHistoryHandler, *args, **kwargs)


def install_operational_history_shared_policy() -> None:
    global _INSTALLED, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
