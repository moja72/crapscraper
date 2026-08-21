from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

import app.addition_custom_fields_policy as field_resolution
import app.addition_full_product_creation_policy as full_creation
import app.addition_one_click_policy as one_click
import app.addition_root_category_policy as root_category
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions
import app.web as web
from app.comparison_decisions import list_approved_additions
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_RENDER = None
_BASE_SERVER = None
_BASE_EMIT = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "addition_operational_ui.js"
_WORKER_LOCK = threading.RLock()
_PREPARATION_WORKER: threading.Thread | None = None
_QUEUE_WORKER: threading.Thread | None = None

_QUEUE_STATES = {
    "waiting": "Aguardando",
    "preparing": "Preparando",
    "ready": "Pronto",
    "queued": "Na fila",
    "executing": "Adicionando",
    "completed": "Concluído",
    "error": "Erro",
    "interrupted": "Interrompido",
    "canceled": "Cancelado",
}
_HISTORY_STATES = {"running", "completed", "error", "interrupted", "canceled"}
_MAX_LOGS = 160

_OPERATION_COLUMNS: dict[str, str] = {
    "approval_active": "INTEGER NOT NULL DEFAULT 1",
    "queue_state": "TEXT NOT NULL DEFAULT 'waiting'",
    "queue_position": "INTEGER NOT NULL DEFAULT 0",
    "enqueue_after_prepare": "INTEGER NOT NULL DEFAULT 0",
    "attempts": "INTEGER NOT NULL DEFAULT 0",
    "active_attempt_id": "INTEGER NOT NULL DEFAULT 0",
    "current_step": "TEXT NOT NULL DEFAULT ''",
    "progress": "INTEGER NOT NULL DEFAULT 0",
    "status_message": "TEXT NOT NULL DEFAULT ''",
    "operation_error": "TEXT NOT NULL DEFAULT ''",
    "started_at": "TEXT NOT NULL DEFAULT ''",
    "finished_at": "TEXT NOT NULL DEFAULT ''",
    "execution_logs": "TEXT NOT NULL DEFAULT '[]'",
    "hidden_from_queue": "INTEGER NOT NULL DEFAULT 0",
    "category_name": "TEXT NOT NULL DEFAULT ''",
    "desenvolvedor": "TEXT NOT NULL DEFAULT ''",
    "site_oficial": "TEXT NOT NULL DEFAULT ''",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_logs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()][-_MAX_LOGS:]
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        return []
    return [str(item) for item in parsed if str(item or "").strip()][-_MAX_LOGS:] if isinstance(parsed, list) else []


def _dump_logs(values: list[str]) -> str:
    return json.dumps([str(item) for item in values[-_MAX_LOGS:]], ensure_ascii=False)


def _ensure_schema() -> None:
    with additions._db() as connection:
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(addition_jobs)").fetchall()
        }
        for name, definition in _OPERATION_COLUMNS.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE addition_jobs ADD COLUMN {name} {definition}")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS addition_attempt_history (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                result TEXT NOT NULL DEFAULT '',
                final_state TEXT NOT NULL DEFAULT '',
                current_step TEXT NOT NULL DEFAULT '',
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                logs TEXT NOT NULL DEFAULT '[]',
                source_name TEXT NOT NULL DEFAULT '',
                source_version TEXT NOT NULL DEFAULT '',
                source_product_url TEXT NOT NULL DEFAULT '',
                source_official_url TEXT NOT NULL DEFAULT '',
                desenvolvedor TEXT NOT NULL DEFAULT '',
                site_oficial TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '',
                category_name TEXT NOT NULL DEFAULT '',
                woo_product_id INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_addition_attempt_job ON addition_attempt_history(job_id, attempt_id DESC);
            CREATE INDEX IF NOT EXISTS idx_addition_attempt_status ON addition_attempt_history(status, attempt_id DESC);

            CREATE TABLE IF NOT EXISTS addition_queue_runtime (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                status TEXT NOT NULL DEFAULT 'stopped',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            INSERT OR IGNORE INTO addition_queue_runtime(singleton, status, updated_at)
            VALUES(1, 'stopped', '');
            """
        )
        connection.execute(
            "UPDATE addition_jobs SET queue_state='completed', progress=100 "
            "WHERE state='completed' AND queue_state='waiting'"
        )
        connection.execute(
            "UPDATE addition_jobs SET queue_state='ready' "
            "WHERE state IN ('ready_to_create','draft_created','published') AND queue_state='waiting'"
        )
        connection.execute(
            "UPDATE addition_jobs SET queue_state='error' "
            "WHERE state IN ('error','blocked') AND queue_state='waiting' AND error <> ''"
        )


def _recover_interrupted_state() -> None:
    _ensure_schema()
    now = _utc_now()
    with additions._db() as connection:
        rows = connection.execute(
            "SELECT job_id, active_attempt_id, queue_state, execution_logs FROM addition_jobs "
            "WHERE queue_state IN ('preparing','executing')"
        ).fetchall()
        for row in rows:
            logs = _load_logs(row["execution_logs"])
            logs.append(f"[{datetime.now().astimezone().strftime('%H:%M:%S')}] Processo interrompido pela reinicialização do CrapScraper.")
            connection.execute(
                "UPDATE addition_jobs SET queue_state='interrupted', current_step='interrupted', "
                "status_message=?, operation_error=?, finished_at=?, execution_logs=? WHERE job_id=?",
                (
                    "Execução interrompida; use Recuperar/Tentar novamente.",
                    "Execução interrompida pela reinicialização do CrapScraper.",
                    now,
                    _dump_logs(logs),
                    str(row["job_id"]),
                ),
            )
            attempt_id = _safe_int(row["active_attempt_id"])
            if attempt_id:
                connection.execute(
                    "UPDATE addition_attempt_history SET status='interrupted', result='Interrompido', "
                    "final_state='interrupted', current_step='interrupted', error=?, logs=?, finished_at=? "
                    "WHERE attempt_id=? AND status='running'",
                    (
                        "Execução interrompida pela reinicialização do CrapScraper.",
                        _dump_logs(logs),
                        now,
                        attempt_id,
                    ),
                )
                connection.execute(
                    "UPDATE addition_jobs SET active_attempt_id=0 WHERE job_id=?",
                    (str(row["job_id"]),),
                )
        connection.execute(
            "UPDATE addition_queue_runtime SET status=CASE WHEN status='running' THEN 'paused' ELSE status END, updated_at=? WHERE singleton=1",
            (now,),
        )


def _queue_runtime() -> dict[str, Any]:
    _ensure_schema()
    with additions._db() as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM addition_queue_runtime WHERE singleton=1"
        ).fetchone()
    status = _clean(row["status"] if row else "stopped") or "stopped"
    return {"status": status, "updated_at": _clean(row["updated_at"] if row else "")}


def _set_queue_runtime(status: str) -> dict[str, Any]:
    normalized = status if status in {"stopped", "running", "paused"} else "stopped"
    now = _utc_now()
    with additions._db() as connection:
        connection.execute(
            "INSERT INTO addition_queue_runtime(singleton,status,updated_at) VALUES(1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
            (normalized, now),
        )
    return {"status": normalized, "updated_at": now}


def _sync_approved_operational() -> dict[str, Any]:
    _ensure_schema()
    approved = [dict(row) for row in list_approved_additions()]
    approved_by_id = {
        _clean(row.get("comparison_item_id")): row
        for row in approved
        if _clean(row.get("comparison_item_id"))
    }
    now = _utc_now()
    created = 0
    changed = 0
    deactivated = 0

    with additions._db() as connection:
        existing_rows = connection.execute("SELECT * FROM addition_jobs").fetchall()
        existing = {str(row["comparison_item_id"]): dict(row) for row in existing_rows}

        for item_id, decision in approved_by_id.items():
            source_name = _clean(decision.get("source_name"))
            source_version = _clean(decision.get("source_version"))
            source_product_url = _clean(decision.get("source_product_url"))
            source_official_url = _clean(decision.get("source_official_url"))
            kind = additions._guess_kind(decision)
            current = existing.get(item_id)
            if current is None:
                import hashlib
                job_id = "add-" + hashlib.sha1(item_id.encode("utf-8")).hexdigest()[:16]
                connection.execute(
                    """
                    INSERT INTO addition_jobs (
                        job_id, comparison_item_id, state, kind, source_name, source_version,
                        source_product_url, source_official_url, title, created_at, updated_at,
                        approval_active, queue_state, status_message
                    ) VALUES (?, ?, 'awaiting_content', ?, ?, ?, ?, ?, ?, ?, ?, 1, 'waiting', 'Aguardando preparação')
                    """,
                    (
                        job_id, item_id, kind, source_name, source_version,
                        source_product_url, source_official_url, source_name, now, now,
                    ),
                )
                created += 1
                continue

            values: dict[str, Any] = {}
            for key, value in (
                ("source_name", source_name),
                ("source_version", source_version),
                ("source_product_url", source_product_url),
                ("kind", kind),
            ):
                if _clean(current.get(key)) != value:
                    values[key] = value
            if source_official_url and not _clean(current.get("source_official_url")):
                values["source_official_url"] = source_official_url
            if _safe_int(current.get("approval_active"), 1) != 1:
                values["approval_active"] = 1
                if _clean(current.get("queue_state")) == "canceled" and not _safe_int(current.get("woo_product_id")):
                    values["queue_state"] = "waiting"
                    values["status_message"] = "Aguardando preparação"
            if values:
                values["updated_at"] = now
                columns = ", ".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE addition_jobs SET {columns} WHERE comparison_item_id=?",
                    tuple(values.values()) + (item_id,),
                )
                changed += 1

        for item_id, current in existing.items():
            if item_id in approved_by_id or _safe_int(current.get("approval_active"), 1) == 0:
                continue
            queue_state = _clean(current.get("queue_state"))
            values: dict[str, Any] = {"approval_active": 0, "updated_at": now}
            if queue_state not in {"preparing", "executing", "completed"}:
                values.update(queue_state="canceled", status_message="Aprovação removida na Comparação")
            columns = ", ".join(f"{key}=?" for key in values)
            connection.execute(
                f"UPDATE addition_jobs SET {columns} WHERE comparison_item_id=?",
                tuple(values.values()) + (item_id,),
            )
            deactivated += 1

    return {
        "ok": True,
        "message": "Adições aprovadas sincronizadas.",
        "approved_total": len(approved_by_id),
        "created": created,
        "changed": changed,
        "deactivated": deactivated,
    }


def _job_snapshot(job_id: str) -> dict[str, Any]:
    _ensure_schema()
    with additions._db() as connection:
        row = connection.execute("SELECT * FROM addition_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Cadastro novo não encontrado.")
    return dict(row)


def _update_operation(job_id: str, **values: Any) -> dict[str, Any]:
    _ensure_schema()
    if not values:
        return _job_snapshot(job_id)
    values["updated_at"] = _utc_now()
    columns = ", ".join(f"{key}=?" for key in values)
    with additions._db() as connection:
        connection.execute(
            f"UPDATE addition_jobs SET {columns} WHERE job_id=?",
            tuple(values.values()) + (job_id,),
        )
    return _job_snapshot(job_id)


def _origin_label(url: Any) -> str:
    value = _clean(url)
    try:
        host = urlsplit(value).hostname or ""
    except Exception:
        host = ""
    host = host.lower().removeprefix("www.")
    if "ultrapack" in host:
        return "UltraPackV2"
    if "plugintheme" in host:
        return "PluginTheme"
    return host or "Origem não identificada"


def _step_label(step: Any) -> str:
    value = _clean(step).lower()
    labels = {
        "": "Aguardando", "waiting": "Aguardando", "starting": "Iniciando",
        "official_source": "Localizando página oficial", "chatgpt": "Conectando ao ChatGPT",
        "chatgpt_description": "Gerando descrição", "description_ready": "Descrição pronta",
        "chatgpt_image": "Gerando imagem", "image_ready": "Imagem pronta",
        "category": "Resolvendo categoria", "pricing": "Resolvendo preços", "zip": "Baixando ZIP",
        "zip_ready": "ZIP validado", "draft": "Criando produto", "draft_ready": "Rascunho pronto",
        "store_validation": "Validando WooCommerce", "publishing": "Publicando", "publish": "Publicando",
        "store_fields": "Validando campos personalizados", "completed": "Concluído",
        "error": "Erro", "interrupted": "Interrompido",
    }
    return labels.get(value, value.replace("_", " ").strip().capitalize() or "Aguardando")


def _queue_state_label(state: Any) -> str:
    return _QUEUE_STATES.get(_clean(state), _clean(state) or "Aguardando")


def _preparation_map(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    image_path = Path(_clean(row.get("image_path"))) if _clean(row.get("image_path")) else None
    zip_path = Path(_clean(row.get("zip_path"))) if _clean(row.get("zip_path")) else None
    return [
        {"key": "source", "label": "Produto de origem", "done": bool(_clean(row.get("source_product_url")))},
        {"key": "version", "label": "Versão", "done": bool(_clean(row.get("source_version")))},
        {"key": "official", "label": "Link oficial", "done": bool(_clean(row.get("source_official_url")) or _clean(row.get("site_oficial")))},
        {"key": "developer", "label": "Desenvolvedor", "done": bool(_clean(row.get("desenvolvedor")))},
        {"key": "description", "label": "Descrição", "done": bool(_clean(row.get("short_description")) and _clean(row.get("description")))},
        {"key": "image", "label": "Imagem", "done": bool(image_path and image_path.is_file())},
        {"key": "category", "label": "Categoria", "done": bool(_clean(row.get("category_name")))},
        {"key": "prices", "label": "Preços", "done": bool(_clean(row.get("annual_regular")) and _clean(row.get("lifetime_regular")))},
        {"key": "zip", "label": "ZIP", "done": bool(zip_path and zip_path.is_file() and _clean(row.get("zip_sha256")))},
    ]


def _prepared_local(row: Mapping[str, Any]) -> bool:
    stages = _preparation_map(row)
    required = {"source", "version", "official", "description", "image", "category", "prices", "zip"}
    return all(item["done"] for item in stages if item["key"] in required)


def _public_operation_job(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    logs = _load_logs(data.get("execution_logs"))
    state = _clean(data.get("queue_state")) or "waiting"
    data.update(
        queue_state=state,
        queue_state_label=_queue_state_label(state),
        current_step_label=_step_label(data.get("current_step")),
        progress=max(0, min(100, _safe_int(data.get("progress")))),
        execution_logs=logs,
        latest_log=logs[-1] if logs else "",
        origin=_origin_label(data.get("source_product_url")),
        kind_label="Tema" if _clean(data.get("kind")) == "theme" else "Plugin",
        preparation=_preparation_map(data),
        prepared=_prepared_local(data),
        approval_active=bool(_safe_int(data.get("approval_active"), 1)),
        hidden_from_queue=bool(_safe_int(data.get("hidden_from_queue"), 0)),
    )
    return data


def _append_persistent_log(job_id: str, message: str, *, step: str = "", progress: int | None = None) -> None:
    try:
        row = _job_snapshot(job_id)
    except Exception:
        return
    logs = _load_logs(row.get("execution_logs"))
    line = f"[{datetime.now().astimezone().strftime('%H:%M:%S')}] {_clean(message)}"
    if _clean(message):
        logs.append(line)
    values: dict[str, Any] = {
        "execution_logs": _dump_logs(logs),
        "status_message": _clean(message) or _clean(row.get("status_message")),
    }
    if step:
        values["current_step"] = _clean(step)
    if progress is not None:
        values["progress"] = max(0, min(100, _safe_int(progress)))
    _update_operation(job_id, **values)

    attempt_id = _safe_int(row.get("active_attempt_id"))
    if attempt_id:
        with additions._db() as connection:
            connection.execute(
                "UPDATE addition_attempt_history SET current_step=?, progress=?, logs=? WHERE attempt_id=? AND status='running'",
                (
                    _clean(step) or _clean(row.get("current_step")),
                    max(0, min(100, _safe_int(progress, _safe_int(row.get("progress"))))),
                    _dump_logs(logs),
                    attempt_id,
                ),
            )


def _persistent_emit(job_id: str, message: str, *, step: str = "", progress: int | None = None) -> None:
    if callable(_BASE_EMIT):
        _BASE_EMIT(job_id, message, step=step, progress=progress)
    _append_persistent_log(job_id, message, step=step, progress=progress)


def _create_attempt(job_id: str) -> int:
    row = _job_snapshot(job_id)
    if _safe_int(row.get("active_attempt_id")):
        raise ValueError("Este produto já possui uma tentativa ativa.")
    attempt_no = _safe_int(row.get("attempts")) + 1
    now = _utc_now()
    with additions._db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO addition_attempt_history (
                job_id, attempt_no, status, result, final_state, current_step, progress,
                error, logs, source_name, source_version, source_product_url,
                source_official_url, desenvolvedor, site_oficial, kind, category_name,
                woo_product_id, started_at, finished_at
            ) VALUES (?, ?, 'running', 'Em andamento', '', 'starting', 0, '', '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
            """,
            (
                job_id, attempt_no, _clean(row.get("source_name")), _clean(row.get("source_version")),
                _clean(row.get("source_product_url")), _clean(row.get("source_official_url")),
                _clean(row.get("desenvolvedor")), _clean(row.get("site_oficial")),
                _clean(row.get("kind")), _clean(row.get("category_name")),
                _safe_int(row.get("woo_product_id")), now,
            ),
        )
        attempt_id = int(cursor.lastrowid)
        connection.execute(
            "UPDATE addition_jobs SET attempts=?, active_attempt_id=?, started_at=?, finished_at='', "
            "operation_error='', execution_logs='[]', progress=0, current_step='starting', updated_at=? WHERE job_id=?",
            (attempt_no, attempt_id, now, now, job_id),
        )
    return attempt_id


def _finish_attempt(job_id: str, status: str, *, error: str = "", result: str = "") -> None:
    row = _job_snapshot(job_id)
    attempt_id = _safe_int(row.get("active_attempt_id"))
    if not attempt_id:
        return
    normalized = status if status in _HISTORY_STATES else "error"
    now = _utc_now()
    logs = _load_logs(row.get("execution_logs"))
    with additions._db() as connection:
        connection.execute(
            """
            UPDATE addition_attempt_history SET
                status=?, result=?, final_state=?, current_step=?, progress=?, error=?, logs=?,
                source_official_url=?, desenvolvedor=?, site_oficial=?, category_name=?, woo_product_id=?, finished_at=?
            WHERE attempt_id=?
            """,
            (
                normalized, result or _queue_state_label(row.get("queue_state")), _clean(row.get("queue_state")),
                _clean(row.get("current_step")), max(0, min(100, _safe_int(row.get("progress")))), _clean(error),
                _dump_logs(logs), _clean(row.get("source_official_url")), _clean(row.get("desenvolvedor")),
                _clean(row.get("site_oficial")), _clean(row.get("category_name")), _safe_int(row.get("woo_product_id")),
                now, attempt_id,
            ),
        )
        connection.execute(
            "UPDATE addition_jobs SET active_attempt_id=0, finished_at=?, updated_at=? WHERE job_id=?",
            (now, now, job_id),
        )


def _resolve_developer_fields(job_id: str) -> None:
    job = additions._row(job_id)
    official = _clean(job.get("source_official_url"))
    if not official:
        return
    developer = _clean(job.get("desenvolvedor"))
    if not developer:
        try:
            developer = _clean(field_resolution._normalize_developer_display(field_resolution._developer(job, official)))
        except Exception:
            developer = ""
    values: dict[str, Any] = {"site_oficial": official}
    if developer:
        values["desenvolvedor"] = developer
    _update_operation(job_id, **values)
    if developer:
        one_click._emit(job_id, f"Desenvolvedor resolvido: {developer}.", step="official_source", progress=77)
    else:
        one_click._emit(
            job_id,
            "Página oficial resolvida; desenvolvedor ainda sem fonte segura e será novamente validado antes/depois da publicação.",
            step="official_source",
            progress=77,
        )


def _prepare_one(job_id: str, manager: Any) -> None:
    row = _job_snapshot(job_id)
    enqueue_after = bool(_safe_int(row.get("enqueue_after_prepare")))
    _update_operation(
        job_id, queue_state="preparing", current_step="starting",
        progress=max(1, _safe_int(row.get("progress"))), status_message="Preparando produto para cadastro",
        operation_error="", hidden_from_queue=0,
    )
    one_click._emit(job_id, "Iniciando preparação do novo produto.", step="starting", progress=2)
    try:
        simple._run_two_chats(job_id)
        _resolve_developer_fields(job_id)
        root_category._prepare_root_category(job_id)
        full_creation._ensure_download_and_prices(job_id, manager)
        job = additions._recalculate_state(job_id)
        current = _job_snapshot(job_id)
        if not _prepared_local(current) and _clean(job.get("state")) not in {"draft_created", "completed"}:
            raise RuntimeError("A preparação terminou, mas os dados persistidos ainda não estão completos para o cadastro.")
        if _clean(job.get("state")) == "completed":
            _update_operation(
                job_id, queue_state="completed", current_step="completed", progress=100,
                status_message="Produto já concluído", enqueue_after_prepare=0, operation_error="",
            )
            _finish_attempt(job_id, "completed", result="Concluído")
            return
        next_state = "queued" if enqueue_after else "ready"
        _update_operation(
            job_id, queue_state=next_state, current_step="zip_ready",
            progress=max(84, _safe_int(current.get("progress"))),
            status_message="Preparação concluída; aguardando execução" if enqueue_after else "Preparação concluída",
            enqueue_after_prepare=0, operation_error="",
        )
        one_click._emit(
            job_id, "Preparação concluída. Produto pronto para entrar na fila de cadastro.",
            step="zip_ready", progress=85,
        )
        if enqueue_after:
            _renumber_queue()
    except Exception as error:
        message = sanitize_text(error)
        try:
            additions._update(job_id, error=message)
        except Exception:
            pass
        _update_operation(
            job_id, queue_state="error", current_step="error", status_message=message,
            operation_error=message, enqueue_after_prepare=0,
        )
        one_click._emit(job_id, f"ERRO na preparação: {message}", step="error")
        _finish_attempt(job_id, "error", error=message, result="Erro na preparação")


def _next_preparation_job() -> str:
    with additions._db() as connection:
        row = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='preparing' "
            "ORDER BY updated_at ASC, created_at ASC LIMIT 1"
        ).fetchone()
    return str(row["job_id"]) if row else ""


def _run_preparation_worker(manager: Any) -> None:
    while True:
        job_id = _next_preparation_job()
        if not job_id:
            return
        _prepare_one(job_id, manager)


def _start_preparation_worker(manager: Any) -> bool:
    global _PREPARATION_WORKER
    with _WORKER_LOCK:
        if _PREPARATION_WORKER and _PREPARATION_WORKER.is_alive():
            return False
        _PREPARATION_WORKER = threading.Thread(
            target=_run_preparation_worker, args=(manager,), daemon=True, name="addition-preparation-queue"
        )
        _PREPARATION_WORKER.start()
        return True


def _renumber_queue() -> None:
    with additions._db() as connection:
        rows = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE queue_state='queued' AND approval_active=1 "
            "ORDER BY CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END, updated_at ASC, created_at ASC"
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute("UPDATE addition_jobs SET queue_position=? WHERE job_id=?", (index, str(row["job_id"])))


def _enqueue_ready(job_id: str) -> None:
    row = _job_snapshot(job_id)
    if not bool(_safe_int(row.get("approval_active"), 1)):
        raise ValueError("A aprovação deste produto não está mais ativa na Comparação.")
    if _clean(row.get("queue_state")) == "completed":
        return
    if not _prepared_local(row) and _clean(row.get("state")) not in {"draft_created", "published"}:
        raise ValueError("O produto ainda precisa passar pela Preparação antes de entrar na fila.")
    _update_operation(
        job_id, queue_state="queued", queue_position=999999, current_step="waiting",
        status_message="Aguardando execução da fila", operation_error="", hidden_from_queue=0,
    )
    _renumber_queue()


def _next_queued_job() -> str:
    with additions._db() as connection:
        row = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='queued' "
            "ORDER BY queue_position ASC, updated_at ASC LIMIT 1"
        ).fetchone()
    return str(row["job_id"]) if row else ""


def _has_pending_pipeline_preparation() -> bool:
    with additions._db() as connection:
        row = connection.execute(
            "SELECT 1 FROM addition_jobs WHERE approval_active=1 AND queue_state='preparing' "
            "AND enqueue_after_prepare=1 LIMIT 1"
        ).fetchone()
    return row is not None


def _execute_one(job_id: str) -> None:
    row = _job_snapshot(job_id)
    if not _safe_int(row.get("active_attempt_id")):
        _create_attempt(job_id)
    _update_operation(
        job_id, queue_state="executing", queue_position=0, current_step="draft",
        progress=max(86, _safe_int(row.get("progress"))), status_message="Criando e validando produto no WooCommerce",
        operation_error="", hidden_from_queue=0,
    )
    one_click._emit(job_id, "Executando cadastro na fila de adições.", step="draft", progress=87)
    try:
        full_creation._create_complete_draft(job_id)
        job = full_creation._publish_complete(job_id)
        product_id = _safe_int(job.get("woo_product_id"))
        _update_operation(
            job_id, queue_state="completed", queue_position=0, current_step="completed", progress=100,
            status_message=f"Produto WooCommerce #{product_id} concluído" if product_id else "Produto concluído",
            operation_error="", finished_at=_utc_now(),
        )
        one_click._emit(job_id, "Produto adicionado e validado com sucesso.", step="completed", progress=100)
        _finish_attempt(job_id, "completed", result="Concluído")
    except Exception as error:
        message = sanitize_text(error)
        try:
            additions._update(job_id, error=message)
        except Exception:
            pass
        _update_operation(
            job_id, queue_state="error", queue_position=0, current_step="error",
            status_message=message, operation_error=message, finished_at=_utc_now(),
        )
        one_click._emit(job_id, f"ERRO na execução: {message}", step="error")
        _finish_attempt(job_id, "error", error=message, result="Erro")
    finally:
        _renumber_queue()


def _run_queue_worker() -> None:
    while True:
        runtime = _queue_runtime()
        if runtime["status"] != "running":
            return
        job_id = _next_queued_job()
        if job_id:
            _execute_one(job_id)
            continue
        if _has_pending_pipeline_preparation():
            time.sleep(0.55)
            continue
        _set_queue_runtime("stopped")
        return


def _start_queue_worker() -> bool:
    global _QUEUE_WORKER
    with _WORKER_LOCK:
        if _QUEUE_WORKER and _QUEUE_WORKER.is_alive():
            return False
        _QUEUE_WORKER = threading.Thread(target=_run_queue_worker, daemon=True, name="addition-execution-queue")
        _QUEUE_WORKER.start()
        return True


def _normalize_job_ids(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("job_ids")
    if not isinstance(raw, list):
        single = _clean(payload.get("job_id"))
        raw = [single] if single else []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        job_id = _clean(value)
        if not job_id or job_id in seen:
            continue
        _job_snapshot(job_id)
        seen.add(job_id)
        result.append(job_id)
    if not result:
        raise ValueError("Selecione pelo menos um produto.")
    return result


def _request_prepare(payload: Mapping[str, Any], manager: Any) -> dict[str, Any]:
    job_ids = _normalize_job_ids(payload)
    accepted = 0
    skipped = 0
    for job_id in job_ids:
        row = _job_snapshot(job_id)
        state = _clean(row.get("queue_state"))
        if not bool(_safe_int(row.get("approval_active"), 1)) or state in {"completed", "executing", "queued", "preparing"}:
            skipped += 1
            continue
        _update_operation(
            job_id, queue_state="preparing", enqueue_after_prepare=0, current_step="starting",
            status_message="Aguardando preparação", operation_error="", hidden_from_queue=0,
        )
        accepted += 1
    if accepted:
        _start_preparation_worker(manager)
    return {"ok": True, "message": f"{accepted} produto(s) enviado(s) para preparação.", "accepted": accepted, "skipped": skipped}


def _request_add(payload: Mapping[str, Any], manager: Any, *, retry: bool = False) -> dict[str, Any]:
    job_ids = _normalize_job_ids(payload)
    accepted = 0
    skipped = 0
    for job_id in job_ids:
        row = _job_snapshot(job_id)
        state = _clean(row.get("queue_state"))
        if not bool(_safe_int(row.get("approval_active"), 1)) or state in {"preparing", "queued", "executing", "completed"}:
            skipped += 1
            continue
        if _safe_int(row.get("active_attempt_id")):
            skipped += 1
            continue
        _create_attempt(job_id)
        row = _job_snapshot(job_id)
        if _prepared_local(row) or _clean(row.get("state")) in {"draft_created", "published"}:
            _enqueue_ready(job_id)
        else:
            _update_operation(
                job_id, queue_state="preparing", enqueue_after_prepare=1, current_step="starting",
                status_message="Preparação iniciada para cadastro", operation_error="", hidden_from_queue=0,
            )
        accepted += 1
    if accepted:
        _set_queue_runtime("running")
        _start_preparation_worker(manager)
        _start_queue_worker()
    verb = "reprocessado(s)" if retry else "adicionado(s) ao fluxo"
    return {"ok": True, "message": f"{accepted} produto(s) {verb}.", "accepted": accepted, "skipped": skipped, "queue": _queue_runtime()}


def _start_queue() -> dict[str, Any]:
    with additions._db() as connection:
        ready_rows = connection.execute(
            "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='ready' AND hidden_from_queue=0"
        ).fetchall()
    for row in ready_rows:
        job_id = str(row["job_id"])
        if not _safe_int(_job_snapshot(job_id).get("active_attempt_id")):
            _create_attempt(job_id)
        _enqueue_ready(job_id)
    _set_queue_runtime("running")
    started = _start_queue_worker()
    return {"ok": True, "message": "Fila de adições iniciada.", "started": started, "queue": _queue_runtime()}


def _pause_queue() -> dict[str, Any]:
    runtime = _set_queue_runtime("paused")
    return {"ok": True, "message": "Fila pausada após o item atualmente em execução.", "queue": runtime}


def _continue_queue() -> dict[str, Any]:
    _set_queue_runtime("running")
    started = _start_queue_worker()
    return {"ok": True, "message": "Fila de adições retomada.", "started": started, "queue": _queue_runtime()}


def _cancel_jobs(payload: Mapping[str, Any]) -> dict[str, Any]:
    job_ids = _normalize_job_ids(payload)
    canceled = 0
    blocked = 0
    for job_id in job_ids:
        row = _job_snapshot(job_id)
        state = _clean(row.get("queue_state"))
        if state in {"preparing", "executing", "completed"} or _safe_int(row.get("woo_product_id")):
            blocked += 1
            continue
        _update_operation(
            job_id, queue_state="canceled", queue_position=0, current_step="", progress=0,
            status_message="Cancelado pelo usuário", operation_error="",
        )
        if _safe_int(row.get("active_attempt_id")):
            _finish_attempt(job_id, "canceled", result="Cancelado")
        canceled += 1
    _renumber_queue()
    return {"ok": True, "message": f"{canceled} item(ns) cancelado(s); {blocked} protegido(s) por segurança.", "canceled": canceled, "blocked": blocked}


def _clear_completed() -> dict[str, Any]:
    with additions._db() as connection:
        cursor = connection.execute(
            "UPDATE addition_jobs SET hidden_from_queue=1, updated_at=? WHERE queue_state='completed' AND hidden_from_queue=0",
            (_utc_now(),),
        )
        count = max(0, cursor.rowcount)
    return {"ok": True, "message": f"{count} concluído(s) removido(s) da fila visual. O histórico foi preservado.", "hidden": count}


def _recover_jobs(payload: Mapping[str, Any], manager: Any) -> dict[str, Any]:
    raw = payload.get("job_ids")
    if isinstance(raw, list) and raw:
        ids = _normalize_job_ids(payload)
    else:
        with additions._db() as connection:
            ids = [str(row["job_id"]) for row in connection.execute(
                "SELECT job_id FROM addition_jobs WHERE approval_active=1 AND queue_state='interrupted' ORDER BY updated_at"
            ).fetchall()]
        if not ids:
            return {"ok": True, "message": "Nenhum item interrompido para recuperar.", "accepted": 0}
    return _request_add({"job_ids": ids}, manager, retry=True)


def _safe_publish(job_id: str) -> dict[str, Any]:
    row = _job_snapshot(job_id)
    if not _safe_int(row.get("woo_product_id")):
        raise ValueError("Nenhum rascunho WooCommerce está disponível para publicação segura.")
    job = full_creation._publish_complete(job_id)
    _update_operation(
        job_id, queue_state="completed", current_step="completed", progress=100,
        status_message="Produto publicado e validado", operation_error="",
    )
    return {"ok": True, "message": "Produto publicado e validado pelo fluxo completo.", "job": _public_operation_job(_job_snapshot(job_id))}


def _counts() -> dict[str, int]:
    counts = {key: 0 for key in _QUEUE_STATES}
    counts["total"] = 0
    counts["active"] = 0
    with additions._db() as connection:
        rows = connection.execute(
            "SELECT queue_state, COUNT(*) AS total FROM addition_jobs WHERE approval_active=1 GROUP BY queue_state"
        ).fetchall()
    for row in rows:
        state = _clean(row["queue_state"]) or "waiting"
        total = _safe_int(row["total"])
        counts[state] = counts.get(state, 0) + total
        counts["total"] += total
    counts["active"] = counts["preparing"] + counts["queued"] + counts["executing"]
    return counts


def _where_jobs(scope: str, q: str, state: str) -> tuple[str, list[Any]]:
    clauses = ["approval_active=1"]
    values: list[Any] = []
    if scope == "preparation":
        clauses.append("queue_state IN ('waiting','preparing','ready','error','interrupted')")
    elif scope == "queue":
        clauses.append("hidden_from_queue=0")
    if state and state in _QUEUE_STATES:
        clauses.append("queue_state=?")
        values.append(state)
    if q:
        token = f"%{q}%"
        clauses.append("(source_name LIKE ? OR title LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? OR source_product_url LIKE ? OR desenvolvedor LIKE ?)")
        values.extend([token, token, token, token, token])
    return " AND ".join(clauses), values


def _paged_jobs(scope: str, *, q: str = "", state: str = "", page: int = 1, page_size: int = 5) -> dict[str, Any]:
    safe_page = max(1, _safe_int(page, 1))
    safe_size = max(1, min(100, _safe_int(page_size, 5)))
    where, values = _where_jobs(scope, q, state)
    with additions._db() as connection:
        total = _safe_int(connection.execute(f"SELECT COUNT(*) AS total FROM addition_jobs WHERE {where}", values).fetchone()["total"])
        pages = max(1, (total + safe_size - 1) // safe_size)
        safe_page = min(safe_page, pages)
        rows = connection.execute(
            f"SELECT * FROM addition_jobs WHERE {where} "
            "ORDER BY CASE queue_state WHEN 'executing' THEN 0 WHEN 'preparing' THEN 1 WHEN 'queued' THEN 2 WHEN 'ready' THEN 3 WHEN 'error' THEN 4 WHEN 'interrupted' THEN 5 WHEN 'waiting' THEN 6 WHEN 'completed' THEN 7 ELSE 8 END, "
            "CASE WHEN queue_position>0 THEN queue_position ELSE 999999 END, updated_at DESC LIMIT ? OFFSET ?",
            values + [safe_size, (safe_page - 1) * safe_size],
        ).fetchall()
    return {
        "items": [_public_operation_job(dict(row)) for row in rows],
        "total": total, "page": safe_page, "page_size": safe_size, "pages": pages,
    }


def _history_where(q: str, status: str, origin: str) -> tuple[str, list[Any]]:
    clauses = ["1=1"]
    values: list[Any] = []
    if status and status in _HISTORY_STATES:
        clauses.append("status=?")
        values.append(status)
    if q:
        token = f"%{q}%"
        clauses.append("(source_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? OR job_id LIKE ?)")
        values.extend([token, token, token])
    if origin:
        clauses.append("source_product_url LIKE ?")
        values.append(f"%{origin}%")
    return " AND ".join(clauses), values


def _history_page(*, q: str = "", status: str = "", origin: str = "", page: int = 1, page_size: int = 5) -> dict[str, Any]:
    safe_page = max(1, _safe_int(page, 1))
    safe_size = max(1, min(100, _safe_int(page_size, 5)))
    where, values = _history_where(q, status, origin)
    with additions._db() as connection:
        total = _safe_int(connection.execute(f"SELECT COUNT(*) AS total FROM addition_attempt_history WHERE {where}", values).fetchone()["total"])
        pages = max(1, (total + safe_size - 1) // safe_size)
        safe_page = min(safe_page, pages)
        rows = [dict(row) for row in connection.execute(
            f"SELECT * FROM addition_attempt_history WHERE {where} ORDER BY attempt_id DESC LIMIT ? OFFSET ?",
            values + [safe_size, (safe_page - 1) * safe_size],
        ).fetchall()]
    for row in rows:
        row["logs"] = _load_logs(row.get("logs"))
        row["origin"] = _origin_label(row.get("source_product_url"))
        row["status_label"] = {
            "running": "Em andamento", "completed": "Concluído", "error": "Erro",
            "interrupted": "Interrompido", "canceled": "Cancelado",
        }.get(_clean(row.get("status")), _clean(row.get("status")))
        try:
            start = datetime.fromisoformat(_clean(row.get("started_at")))
            end = datetime.fromisoformat(_clean(row.get("finished_at"))) if _clean(row.get("finished_at")) else datetime.now(timezone.utc)
            row["duration_seconds"] = max(0, int((end - start).total_seconds()))
        except Exception:
            row["duration_seconds"] = 0
    return {"items": rows, "total": total, "page": safe_page, "page_size": safe_size, "pages": pages}


def _processes_snapshot() -> list[dict[str, Any]]:
    with additions._db() as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM addition_jobs WHERE approval_active=1 AND queue_state IN ('preparing','executing') ORDER BY updated_at"
        ).fetchall()]
    processes: list[dict[str, Any]] = []
    for row in rows:
        job = _public_operation_job(row)
        preparing = job["queue_state"] == "preparing"
        processes.append({
            "id": f"addition:{job['job_id']}", "job_id": job["job_id"],
            "title": "Preparação de novo produto" if preparing else "Cadastro de novo produto",
            "kind": "addition", "status": job["current_step_label"],
            "detail": job.get("title") or job.get("source_name") or job["job_id"],
            "started_at": job.get("started_at") or job.get("updated_at"), "progress": job.get("progress"),
            "latest_log": job.get("latest_log"),
            "meta": f"{job.get('origin')} · {job.get('kind_label')}" + (f" · Woo #{job.get('woo_product_id')}" if job.get("woo_product_id") else ""),
        })
    return processes


def _dashboard_payload() -> dict[str, Any]:
    return {"ok": True, "counts": _counts(), "queue": _queue_runtime(), "processes": _processes_snapshot()}


def _query_value(query: Mapping[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key) or []
    return _clean(values[0]) if values else default


def _operations_payload(path_query: str) -> dict[str, Any]:
    query = parse_qs(path_query, keep_blank_values=True)
    scope = _query_value(query, "scope", "overview")
    if scope in {"overview", "processes"}:
        payload = _dashboard_payload()
        if scope == "processes":
            return {"ok": True, "processes": payload["processes"], "queue": payload["queue"]}
        return payload
    if scope in {"preparation", "queue"}:
        return {"ok": True, **_paged_jobs(
            scope, q=_query_value(query, "q"), state=_query_value(query, "state"),
            page=_safe_int(_query_value(query, "page", "1"), 1),
            page_size=_safe_int(_query_value(query, "page_size", "5"), 5),
        )}
    if scope == "history":
        return {"ok": True, **_history_page(
            q=_query_value(query, "q"), status=_query_value(query, "state"), origin=_query_value(query, "origin"),
            page=_safe_int(_query_value(query, "page", "1"), 1),
            page_size=_safe_int(_query_value(query, "page_size", "5"), 5),
        )}
    raise ValueError("Escopo de adições inválido.")


def _history_csv(path_query: str) -> bytes:
    query = parse_qs(path_query, keep_blank_values=True)
    where, values = _history_where(_query_value(query, "q"), _query_value(query, "state"), _query_value(query, "origin"))
    with additions._db() as connection:
        rows = [dict(row) for row in connection.execute(
            f"SELECT * FROM addition_attempt_history WHERE {where} ORDER BY attempt_id DESC LIMIT 10000", values
        ).fetchall()]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow([
        "Tentativa", "Job", "Produto", "WooCommerce ID", "Origem", "Versão", "Tipo",
        "Categoria", "Desenvolvedor", "Link oficial", "Início", "Fim", "Resultado", "Estado", "Erro",
    ])
    for row in rows:
        writer.writerow([
            row.get("attempt_no", ""), row.get("job_id", ""), row.get("source_name", ""), row.get("woo_product_id", ""),
            _origin_label(row.get("source_product_url")), row.get("source_version", ""), row.get("kind", ""),
            row.get("category_name", ""), row.get("desenvolvedor", ""), row.get("site_oficial") or row.get("source_official_url", ""),
            row.get("started_at", ""), row.get("finished_at", ""), row.get("result", ""), row.get("status", ""), row.get("error", ""),
        ])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _item_payload(job_id: str) -> dict[str, Any]:
    row = _job_snapshot(job_id)
    public = _public_operation_job(row)
    try:
        public["prompt"] = additions._public_job(additions._row(job_id)).get("prompt", "")
    except Exception:
        public["prompt"] = ""
    return {"ok": True, "job": public}


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-addition-operational-ui>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _manager_from_handler(handler_class: type) -> Any:
    try:
        return additions._manager_from_handler(handler_class)
    except Exception:
        return None


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)

    class AdditionOperationalHandler(handler_class):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path or "/"
            if path == "/adicoes/operacoes":
                try:
                    self._send_json(_operations_payload(parsed.query))
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            if path == "/adicoes/operacoes/item":
                try:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    self._send_json(_item_payload(_query_value(query, "job_id")))
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=404)
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            if path == "/adicoes/operacoes/historico.csv":
                try:
                    self._send_bytes(_history_csv(parsed.query), content_type="text/csv; charset=utf-8")
                except Exception as error:
                    self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if not path.startswith("/adicoes/operacoes/") and not path.startswith("/adicoes/fila/"):
                return super().do_POST()
            try:
                payload = self._read_json_body()
                if path == "/adicoes/operacoes/sincronizar":
                    result = _sync_approved_operational()
                elif path == "/adicoes/operacoes/preparar":
                    result = _request_prepare(payload, manager)
                elif path == "/adicoes/fila/adicionar":
                    result = _request_add(payload, manager)
                elif path == "/adicoes/fila/retry":
                    result = _request_add(payload, manager, retry=True)
                elif path == "/adicoes/fila/iniciar":
                    result = _start_queue()
                elif path == "/adicoes/fila/pausar":
                    result = _pause_queue()
                elif path == "/adicoes/fila/continuar":
                    result = _continue_queue()
                elif path == "/adicoes/fila/cancelar":
                    result = _cancel_jobs(payload)
                elif path == "/adicoes/fila/limpar-concluidos":
                    result = _clear_completed()
                elif path == "/adicoes/fila/recuperar":
                    result = _recover_jobs(payload, manager)
                elif path == "/adicoes/operacoes/publicar":
                    result = _safe_publish(_clean(payload.get("job_id")))
                else:
                    self._send_json({"ok": False, "message": "Operação de adição não encontrada."}, code=404)
                    return
                self._send_json(result)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, AdditionOperationalHandler, *args, **kwargs)


def install_addition_operational_ui_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER, _BASE_EMIT
    if _INSTALLED:
        return
    _ensure_schema()
    _recover_interrupted_state()
    _sync_approved_operational()

    _BASE_EMIT = one_click._emit
    one_click._emit = _persistent_emit

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
