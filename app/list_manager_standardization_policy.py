from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit

import app.addition_operational_ui_policy as operational
import app.addition_queue_lists_policy as addition_lists
import app.new_product_workflow_policy as additions
import app.web as web
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "list_manager_standardization.js"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _queue_filename(name: str) -> str:
    normalized = _clean(name) or "default"
    if normalized == "default":
        return "default.csv"
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "lista"
    return f"{slug}.csv"


def _enriched_lists_snapshot() -> dict[str, Any]:
    snapshot = addition_lists._lists_snapshot()
    queues = [dict(item) for item in snapshot.get("queues", []) if isinstance(item, Mapping)]
    with additions._db() as connection:
        rows = connection.execute(
            """
            SELECT queue_name,
                   SUM(CASE WHEN queue_state='canceled' THEN 1 ELSE 0 END) AS canceled,
                   SUM(CASE WHEN queue_state NOT IN ('completed','canceled') THEN 1 ELSE 0 END) AS pending,
                   MAX(CASE WHEN queue_state='completed' THEN COALESCE(NULLIF(finished_at,''), updated_at, '') ELSE '' END) AS last_completion
            FROM addition_jobs
            WHERE approval_active=1
            GROUP BY queue_name
            """
        ).fetchall()
    extra = {(_clean(row["queue_name"]) or "default"): dict(row) for row in rows}
    for queue in queues:
        name = _clean(queue.get("name")) or "default"
        values = extra.get(name, {})
        queue["pending"] = _safe_int(values.get("pending"))
        queue["canceled"] = _safe_int(values.get("canceled"))
        queue["last_completion"] = _clean(values.get("last_completion"))
        queue["file_name"] = _queue_filename(name)
    snapshot["queues"] = queues
    return snapshot


def _validate_list_name(name: Any) -> str:
    target = addition_lists._safe_name(name)
    if not addition_lists._list_exists(target):
        raise ValueError("Lista de adições não encontrada.")
    return target


def _list_detail(name: Any, q: str = "", page: int = 1, page_size: int = 5) -> dict[str, Any]:
    target = _validate_list_name(name)
    token = _clean(q)
    page_size = max(1, min(100, _safe_int(page_size, 5)))
    page = max(1, _safe_int(page, 1))
    clauses = ["approval_active=1", "queue_name=?"]
    values: list[Any] = [target]
    if token:
        like = f"%{token}%"
        clauses.append(
            "(source_name LIKE ? OR title LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? "
            "OR queue_state LIKE ? OR current_step LIKE ? OR desenvolvedor LIKE ? OR source_product_url LIKE ?)"
        )
        values.extend([like] * 7)
    where = " AND ".join(clauses)
    with additions._db() as connection:
        total_row = connection.execute(f"SELECT COUNT(*) AS total FROM addition_jobs WHERE {where}", values).fetchone()
        total = _safe_int(total_row["total"] if total_row else 0)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        offset = (page - 1) * page_size
        rows = connection.execute(
            f"""
            SELECT job_id, queue_position, woo_product_id, source_name, title, queue_state,
                   source_version, source_product_url, desenvolvedor, current_step,
                   finished_at, updated_at
            FROM addition_jobs
            WHERE {where}
            ORDER BY CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END,
                     CASE WHEN queue_state='completed' THEN 1 ELSE 0 END,
                     updated_at DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*values, page_size, offset],
        ).fetchall()
    snapshot = _enriched_lists_snapshot()
    queue = next((item for item in snapshot.get("queues", []) if _clean(item.get("name")) == target), None)
    items: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        state = _clean(row.get("queue_state")) or "waiting"
        source_url = _clean(row.get("source_product_url"))
        items.append({
            "job_id": _clean(row.get("job_id")),
            "position": _safe_int(row.get("queue_position")),
            "woo_product_id": _safe_int(row.get("woo_product_id")),
            "product": _clean(row.get("title")) or _clean(row.get("source_name")) or "Produto sem nome",
            "state": state,
            "state_label": operational._queue_state_label(state),
            "version": _clean(row.get("source_version")) or "—",
            "origin": operational._origin_label(source_url),
            "developer": _clean(row.get("desenvolvedor")) or "—",
            "last_step": _clean(row.get("current_step")),
            "last_step_label": operational._step_label(row.get("current_step")),
            "finished_at": _clean(row.get("finished_at")),
            "updated_at": _clean(row.get("updated_at")),
        })
    return {
        "ok": True,
        "name": target,
        "label": "Padrão" if target == "default" else target,
        "active_queue": snapshot.get("active_queue", "default"),
        "summary": queue or {"name": target, "label": target, "total": total, "completed": 0, "pending": total, "file_name": _queue_filename(target)},
        "q": token,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "total": total,
        "items": items,
    }


def _csv_bytes(name: Any) -> bytes:
    target = _validate_list_name(name)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "posicao", "woo_id", "produto", "estado", "versao", "origem",
        "desenvolvedor", "ultima_etapa", "conclusao", "job_id",
    ])
    with additions._db() as connection:
        rows = connection.execute(
            """
            SELECT job_id, queue_position, woo_product_id, source_name, title, queue_state,
                   source_version, source_product_url, desenvolvedor, current_step,
                   finished_at, updated_at
            FROM addition_jobs
            WHERE approval_active=1 AND queue_name=?
            ORDER BY CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END,
                     updated_at DESC, created_at DESC
            """,
            (target,),
        ).fetchall()
    for raw in rows:
        row = dict(raw)
        state = _clean(row.get("queue_state")) or "waiting"
        writer.writerow([
            _safe_int(row.get("queue_position")) or "",
            _safe_int(row.get("woo_product_id")) or "",
            _clean(row.get("title")) or _clean(row.get("source_name")),
            operational._queue_state_label(state),
            _clean(row.get("source_version")),
            operational._origin_label(row.get("source_product_url")),
            _clean(row.get("desenvolvedor")),
            operational._step_label(row.get("current_step")),
            _clean(row.get("finished_at")) or _clean(row.get("updated_at")),
            _clean(row.get("job_id")),
        ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _clear_list_items(name: Any) -> dict[str, Any]:
    target = _validate_list_name(name)
    addition_lists._assert_can_switch()
    now = operational._utc_now()
    with additions._db() as connection:
        cursor = connection.execute(
            """
            UPDATE addition_jobs
               SET queue_name='', queue_position=0, hidden_from_queue=1, updated_at=?
             WHERE approval_active=1 AND queue_name=? AND queue_state IN ('completed','canceled')
            """,
            (now, target),
        )
        removed = max(0, cursor.rowcount)
        pending_row = connection.execute(
            "SELECT COUNT(*) AS total FROM addition_jobs WHERE approval_active=1 AND queue_name=?",
            (target,),
        ).fetchone()
        pending = _safe_int(pending_row["total"] if pending_row else 0)
    addition_lists._clear_operational_cache()
    return {
        "ok": True,
        "message": f"{removed} item(ns) concluído(s)/cancelado(s) removido(s) da lista. O histórico foi preservado.",
        "removed": removed,
        "remaining": pending,
        **_enriched_lists_snapshot(),
    }


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class CanonicalAdditionListManagerHandler(handler_class):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path or "/"
            params = parse_qs(parsed.query)
            try:
                if path == "/adicoes/fila/listas":
                    self._send_json(_enriched_lists_snapshot())
                    return
                if path == "/adicoes/fila/listas/detalhe":
                    self._send_json(_list_detail(
                        params.get("name", ["default"])[0],
                        params.get("q", [""])[0],
                        _safe_int(params.get("page", [1])[0], 1),
                        _safe_int(params.get("page_size", [5])[0], 5),
                    ))
                    return
                if path == "/adicoes/fila/listas/csv":
                    name = params.get("name", ["default"])[0]
                    data = _csv_bytes(name)
                    filename = _queue_filename(_validate_list_name(name))
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
                return
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path != "/adicoes/fila/listas/limpar":
                return super().do_POST()
            try:
                payload = self._read_json_body()
                self._send_json(_clear_list_items(payload.get("name")))
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, CanonicalAdditionListManagerHandler, *args, **kwargs)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-list-manager-standardization>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_list_manager_standardization_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
