from __future__ import annotations

import threading
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import app.addition_operational_ui_policy as operational
import app.addition_operational_performance_policy as performance
import app.new_product_workflow_policy as additions
import app.web as web
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_SERVER: Any = None
_BASE_ENSURE_SCHEMA: Callable[[], None] | None = None
_BASE_QUEUE_RUNTIME: Callable[[], dict[str, Any]] | None = None
_BASE_RECOVER_JOBS: Callable[..., dict[str, Any]] | None = None
_LIST_LOCK = threading.RLock()
_DEFAULT_QUEUE = "default"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_name(value: Any) -> str:
    name = _clean(value)
    if not name:
        raise ValueError("Informe um nome para a lista.")
    if len(name) > 60:
        raise ValueError("O nome da lista pode ter no máximo 60 caracteres.")
    if name.lower() in {"padrao", "padrão"}:
        return _DEFAULT_QUEUE
    return name


def _clear_operational_cache() -> None:
    try:
        with performance._CACHE_LOCK:
            performance._CACHE.clear()
    except Exception:
        pass


def _ensure_schema_with_lists() -> None:
    if _BASE_ENSURE_SCHEMA is not None:
        _BASE_ENSURE_SCHEMA()
    now = operational._utc_now()
    with additions._db() as connection:
        job_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(addition_jobs)").fetchall()}
        if "queue_name" not in job_columns:
            connection.execute("ALTER TABLE addition_jobs ADD COLUMN queue_name TEXT NOT NULL DEFAULT 'default'")

        runtime_columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(addition_queue_runtime)").fetchall()}
        if "active_queue" not in runtime_columns:
            connection.execute("ALTER TABLE addition_queue_runtime ADD COLUMN active_queue TEXT NOT NULL DEFAULT 'default'")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS addition_queue_lists (
                name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO addition_queue_lists(name, created_at, updated_at) VALUES(?, ?, ?)",
            (_DEFAULT_QUEUE, now, now),
        )
        connection.execute(
            "UPDATE addition_jobs SET queue_name=? WHERE queue_name IS NULL OR TRIM(queue_name)=''",
            (_DEFAULT_QUEUE,),
        )
        connection.execute(
            "UPDATE addition_queue_runtime SET active_queue=? WHERE active_queue IS NULL OR TRIM(active_queue)=''",
            (_DEFAULT_QUEUE,),
        )
        row = connection.execute("SELECT active_queue FROM addition_queue_runtime WHERE singleton=1").fetchone()
        active = _clean(row["active_queue"] if row else _DEFAULT_QUEUE) or _DEFAULT_QUEUE
        connection.execute(
            "INSERT OR IGNORE INTO addition_queue_lists(name, created_at, updated_at) VALUES(?, ?, ?)",
            (active, now, now),
        )


def _active_queue() -> str:
    _ensure_schema_with_lists()
    with additions._db() as connection:
        row = connection.execute("SELECT active_queue FROM addition_queue_runtime WHERE singleton=1").fetchone()
    return _clean(row["active_queue"] if row else _DEFAULT_QUEUE) or _DEFAULT_QUEUE


def _queue_list_rows() -> list[dict[str, Any]]:
    _ensure_schema_with_lists()
    with additions._db() as connection:
        rows = [dict(row) for row in connection.execute(
            """
            SELECT l.name, l.created_at, l.updated_at,
                   COUNT(j.job_id) AS total,
                   SUM(CASE WHEN j.queue_state='waiting' THEN 1 ELSE 0 END) AS waiting,
                   SUM(CASE WHEN j.queue_state='ready' THEN 1 ELSE 0 END) AS ready,
                   SUM(CASE WHEN j.queue_state='queued' THEN 1 ELSE 0 END) AS queued,
                   SUM(CASE WHEN j.queue_state='executing' THEN 1 ELSE 0 END) AS executing,
                   SUM(CASE WHEN j.queue_state='completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN j.queue_state IN ('error','interrupted') THEN 1 ELSE 0 END) AS errors
            FROM addition_queue_lists l
            LEFT JOIN addition_jobs j ON j.queue_name=l.name AND j.approval_active=1
            GROUP BY l.name, l.created_at, l.updated_at
            ORDER BY CASE WHEN l.name='default' THEN 0 ELSE 1 END, LOWER(l.name)
            """
        ).fetchall()]
    for row in rows:
        for key in ("total", "waiting", "ready", "queued", "executing", "completed", "errors"):
            row[key] = int(row.get(key) or 0)
        row["label"] = "Padrão" if row["name"] == _DEFAULT_QUEUE else row["name"]
    return rows


def _lists_snapshot() -> dict[str, Any]:
    runtime = _BASE_QUEUE_RUNTIME() if _BASE_QUEUE_RUNTIME is not None else {"status": "stopped", "updated_at": ""}
    active = _active_queue()
    queues = _queue_list_rows()
    return {
        "ok": True,
        "active_queue": active,
        "active_label": "Padrão" if active == _DEFAULT_QUEUE else active,
        "status": str(runtime.get("status") or "stopped"),
        "updated_at": str(runtime.get("updated_at") or ""),
        "queues": queues,
    }


def _queue_runtime_scoped() -> dict[str, Any]:
    runtime = _BASE_QUEUE_RUNTIME() if _BASE_QUEUE_RUNTIME is not None else {"status": "stopped", "updated_at": ""}
    snapshot = _lists_snapshot()
    runtime.update(
        active_queue=snapshot["active_queue"],
        active_label=snapshot["active_label"],
        queues=snapshot["queues"],
    )
    return runtime


def _counts_scoped() -> dict[str, int]:
    _ensure_schema_with_lists()
    active = _active_queue()
    counts = {key: 0 for key in operational._QUEUE_STATES}
    counts["total"] = 0
    counts["active"] = 0
    with additions._db() as connection:
        rows = connection.execute(
            "SELECT queue_state, COUNT(*) AS total FROM addition_jobs "
            "WHERE approval_active=1 AND queue_name=? GROUP BY queue_state",
            (active,),
        ).fetchall()
    for row in rows:
        state = operational._clean(row["queue_state"]) or "waiting"
        total = operational._safe_int(row["total"])
        counts[state] = counts.get(state, 0) + total
        counts["total"] += total
    counts["active"] = counts["preparing"] + counts["queued"] + counts["executing"]
    return counts


def _where_jobs_scoped(scope: str, q: str, state: str) -> tuple[str, list[Any]]:
    active = _active_queue()
    clauses = ["approval_active=1", "queue_name=?"]
    values: list[Any] = [active]
    if scope == "preparation":
        clauses.append("queue_state IN ('waiting','preparing','ready','error','interrupted')")
    elif scope == "queue":
        clauses.append("hidden_from_queue=0")
    if state and state in operational._QUEUE_STATES:
        clauses.append("queue_state=?")
        values.append(state)
    if q:
        token = f"%{q}%"
        clauses.append("(source_name LIKE ? OR title LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? OR source_product_url LIKE ? OR desenvolvedor LIKE ?)")
        values.extend([token, token, token, token, token])
    return " AND ".join(clauses), values


def _renumber_queue_scoped() -> None:
    active = _active_queue()
    with additions._db() as connection:
        rows = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE queue_state='queued' AND approval_active=1 AND queue_name=? "
            "ORDER BY CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END, updated_at ASC, created_at ASC",
            (active,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute("UPDATE addition_jobs SET queue_position=? WHERE job_id=?", (index, str(row["job_id"])))


def _next_preparation_job_scoped() -> str:
    active = _active_queue()
    with additions._db() as connection:
        row = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='preparing' AND queue_name=? "
            "ORDER BY updated_at ASC, created_at ASC LIMIT 1",
            (active,),
        ).fetchone()
    return str(row["job_id"]) if row else ""


def _next_queued_job_scoped() -> str:
    active = _active_queue()
    with additions._db() as connection:
        row = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='queued' AND queue_name=? "
            "ORDER BY CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END, updated_at ASC LIMIT 1",
            (active,),
        ).fetchone()
    return str(row["job_id"]) if row else ""


def _has_pending_pipeline_preparation_scoped() -> bool:
    active = _active_queue()
    with additions._db() as connection:
        row = connection.execute(
            "SELECT 1 FROM addition_jobs WHERE approval_active=1 AND queue_state='preparing' "
            "AND enqueue_after_prepare=1 AND queue_name=? LIMIT 1",
            (active,),
        ).fetchone()
    return row is not None


def _start_queue_scoped() -> dict[str, Any]:
    active = _active_queue()
    with additions._db() as connection:
        ready_rows = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='ready' "
            "AND hidden_from_queue=0 AND queue_name=?",
            (active,),
        ).fetchall()
    for row in ready_rows:
        job_id = str(row["job_id"])
        if not operational._safe_int(operational._job_snapshot(job_id).get("active_attempt_id")):
            operational._create_attempt(job_id)
        operational._enqueue_ready(job_id)
    operational._set_queue_runtime("running")
    started = operational._start_queue_worker()
    _clear_operational_cache()
    return {
        "ok": True,
        "message": f"Fila de adições '{'Padrão' if active == _DEFAULT_QUEUE else active}' iniciada.",
        "started": started,
        "queue": _queue_runtime_scoped(),
    }


def _recover_jobs_scoped(payload: Mapping[str, Any], manager: Any) -> dict[str, Any]:
    raw = payload.get("job_ids")
    if isinstance(raw, list) and raw:
        if _BASE_RECOVER_JOBS is None:
            raise RuntimeError("Recuperação base indisponível.")
        return _BASE_RECOVER_JOBS(payload, manager)
    active = _active_queue()
    with additions._db() as connection:
        ids = [str(row["job_id"]) for row in connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='interrupted' "
            "AND queue_name=? ORDER BY updated_at",
            (active,),
        ).fetchall()]
    if not ids:
        return {"ok": True, "message": "Nenhum item interrompido para recuperar nesta lista.", "accepted": 0}
    return operational._request_add({"job_ids": ids}, manager, retry=True)


def _clear_completed_scoped() -> dict[str, Any]:
    active = _active_queue()
    with additions._db() as connection:
        cursor = connection.execute(
            "UPDATE addition_jobs SET hidden_from_queue=1, updated_at=? "
            "WHERE queue_state='completed' AND hidden_from_queue=0 AND queue_name=?",
            (operational._utc_now(), active),
        )
        count = max(0, cursor.rowcount)
    _clear_operational_cache()
    return {"ok": True, "message": f"{count} concluído(s) removido(s) da lista ativa. O histórico foi preservado.", "hidden": count}


def _assert_can_switch() -> None:
    runtime = _BASE_QUEUE_RUNTIME() if _BASE_QUEUE_RUNTIME is not None else {"status": "stopped"}
    if str(runtime.get("status") or "stopped") == "running":
        raise ValueError("Pause a fila antes de trocar ou gerenciar a lista ativa.")
    with additions._db() as connection:
        row = connection.execute(
            "SELECT 1 FROM addition_jobs WHERE queue_state IN ('preparing','executing') LIMIT 1"
        ).fetchone()
    if row is not None:
        raise ValueError("Aguarde a preparação/execução atual terminar antes de trocar listas.")


def _list_exists(name: str) -> bool:
    with additions._db() as connection:
        return connection.execute("SELECT 1 FROM addition_queue_lists WHERE name=?", (name,)).fetchone() is not None


def _select_list(name: str) -> dict[str, Any]:
    _ensure_schema_with_lists()
    target = _safe_name(name)
    if not _list_exists(target):
        raise ValueError("Lista de adições não encontrada.")
    _assert_can_switch()
    now = operational._utc_now()
    with additions._db() as connection:
        connection.execute(
            "UPDATE addition_queue_runtime SET active_queue=?, status='stopped', updated_at=? WHERE singleton=1",
            (target, now),
        )
        connection.execute("UPDATE addition_queue_lists SET updated_at=? WHERE name=?", (now, target))
    _clear_operational_cache()
    return {"ok": True, "message": f"Lista ativa: {'Padrão' if target == _DEFAULT_QUEUE else target}.", **_lists_snapshot()}


def _create_list(name: str, *, activate: bool = False) -> dict[str, Any]:
    _ensure_schema_with_lists()
    target = _safe_name(name)
    now = operational._utc_now()
    with _LIST_LOCK, additions._db() as connection:
        if connection.execute("SELECT 1 FROM addition_queue_lists WHERE name=?", (target,)).fetchone():
            raise ValueError("Já existe uma lista com esse nome.")
        connection.execute(
            "INSERT INTO addition_queue_lists(name, created_at, updated_at) VALUES(?, ?, ?)",
            (target, now, now),
        )
    if activate:
        return _select_list(target)
    _clear_operational_cache()
    return {"ok": True, "message": "Lista criada.", **_lists_snapshot()}


def _rename_list(old_name: str, new_name: str) -> dict[str, Any]:
    _ensure_schema_with_lists()
    old = _safe_name(old_name)
    new = _safe_name(new_name)
    if old == _DEFAULT_QUEUE:
        raise ValueError("A lista Padrão não pode ser renomeada.")
    if old == new:
        return {"ok": True, "message": "O nome da lista não mudou.", **_lists_snapshot()}
    _assert_can_switch()
    if not _list_exists(old):
        raise ValueError("Lista de adições não encontrada.")
    if _list_exists(new):
        raise ValueError("Já existe uma lista com esse nome.")
    now = operational._utc_now()
    with additions._db() as connection:
        connection.execute("UPDATE addition_queue_lists SET name=?, updated_at=? WHERE name=?", (new, now, old))
        connection.execute("UPDATE addition_jobs SET queue_name=?, updated_at=? WHERE queue_name=?", (new, now, old))
        connection.execute("UPDATE addition_queue_runtime SET active_queue=? WHERE active_queue=?", (new, old))
    _clear_operational_cache()
    return {"ok": True, "message": "Lista renomeada.", **_lists_snapshot()}


def _delete_list(name: str) -> dict[str, Any]:
    _ensure_schema_with_lists()
    target = _safe_name(name)
    if target == _DEFAULT_QUEUE:
        raise ValueError("A lista Padrão não pode ser excluída.")
    active = _active_queue()
    if target == active:
        raise ValueError("Ative outra lista antes de excluir esta.")
    _assert_can_switch()
    if not _list_exists(target):
        raise ValueError("Lista de adições não encontrada.")
    now = operational._utc_now()
    with additions._db() as connection:
        connection.execute(
            "UPDATE addition_jobs SET queue_name=?, queue_position=0, updated_at=? WHERE queue_name=?",
            (_DEFAULT_QUEUE, now, target),
        )
        connection.execute("DELETE FROM addition_queue_lists WHERE name=?", (target,))
    _clear_operational_cache()
    return {"ok": True, "message": "Lista excluída; seus itens voltaram para Padrão.", **_lists_snapshot()}


def _move_jobs(payload: Mapping[str, Any]) -> dict[str, Any]:
    _ensure_schema_with_lists()
    target = _safe_name(payload.get("target"))
    raw = payload.get("job_ids")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Selecione ao menos um item da fila para mover.")
    if not _list_exists(target):
        raise ValueError("Lista de destino não encontrada.")
    _assert_can_switch()
    ids = [operational._clean(item) for item in raw if operational._clean(item)]
    if not ids:
        raise ValueError("Selecione ao menos um item da fila para mover.")
    placeholders = ",".join("?" for _ in ids)
    now = operational._utc_now()
    with additions._db() as connection:
        blocked = connection.execute(
            f"SELECT COUNT(*) AS total FROM addition_jobs WHERE job_id IN ({placeholders}) "
            "AND queue_state IN ('preparing','executing')",
            ids,
        ).fetchone()
        if int(blocked["total"] or 0):
            raise ValueError("Itens em preparação ou execução não podem ser movidos entre listas.")
        cursor = connection.execute(
            f"UPDATE addition_jobs SET queue_name=?, queue_position=0, updated_at=? "
            f"WHERE job_id IN ({placeholders}) AND approval_active=1",
            [target, now, *ids],
        )
        moved = max(0, cursor.rowcount)
    operational._renumber_queue()
    _clear_operational_cache()
    return {"ok": True, "message": f"{moved} item(ns) movido(s) para {'Padrão' if target == _DEFAULT_QUEUE else target}.", "moved": moved, **_lists_snapshot()}


def _clear_history() -> dict[str, Any]:
    _ensure_schema_with_lists()
    with additions._db() as connection:
        cursor = connection.execute("DELETE FROM addition_attempt_history")
        removed = max(0, cursor.rowcount)
    _clear_operational_cache()
    return {"ok": True, "message": f"{removed} registro(s) removido(s) do histórico de adições.", "removed": removed}


def _handle_list_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    action = _clean(payload.get("action")).lower()
    if action == "create":
        return _create_list(_clean(payload.get("name")), activate=bool(payload.get("activate")))
    if action == "select":
        return _select_list(_clean(payload.get("name")))
    if action == "rename":
        return _rename_list(_clean(payload.get("name")), _clean(payload.get("new_name")))
    if action == "delete":
        return _delete_list(_clean(payload.get("name")))
    if action == "move":
        return _move_jobs(payload)
    raise ValueError("Ação de lista de adições inválida.")


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class AdditionQueueListsHandler(handler_class):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path or "/"
            if path == "/adicoes/fila/listas":
                try:
                    self._send_json(_lists_snapshot())
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path not in {"/adicoes/fila/listas", "/adicoes/operacoes/historico/limpar"}:
                return super().do_POST()
            try:
                payload = self._read_json_body()
                result = _clear_history() if path.endswith("/historico/limpar") else _handle_list_action(payload)
                self._send_json(result)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, AdditionQueueListsHandler, *args, **kwargs)


def install_addition_queue_lists_policy() -> None:
    global _INSTALLED, _BASE_SERVER, _BASE_ENSURE_SCHEMA, _BASE_QUEUE_RUNTIME, _BASE_RECOVER_JOBS
    if _INSTALLED:
        return

    _BASE_ENSURE_SCHEMA = operational._ensure_schema
    _BASE_QUEUE_RUNTIME = operational._queue_runtime
    _BASE_RECOVER_JOBS = operational._recover_jobs
    _ensure_schema_with_lists()

    operational._ensure_schema = _ensure_schema_with_lists
    operational._queue_runtime = _queue_runtime_scoped
    operational._counts = _counts_scoped
    operational._where_jobs = _where_jobs_scoped
    operational._renumber_queue = _renumber_queue_scoped
    operational._next_preparation_job = _next_preparation_job_scoped
    operational._next_queued_job = _next_queued_job_scoped
    operational._has_pending_pipeline_preparation = _has_pending_pipeline_preparation_scoped
    operational._start_queue = _start_queue_scoped
    operational._recover_jobs = _recover_jobs_scoped
    operational._clear_completed = _clear_completed_scoped

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
