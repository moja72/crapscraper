from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

import app.addition_operational_ui_policy as addition_ui
import app.addition_product_creative_policy as creative
import app.new_product_workflow_policy as additions
import app.operations.runtime as update_runtime
import app.web as web

_INSTALLED = False
_BASE_REFERENCE_PATH: Callable[[Mapping[str, Any]], Path] | None = None
_BASE_ATTACH_REFERENCE: Callable[[Any, Path, str], bool] | None = None
_BASE_HISTORY_PAGE: Callable[..., dict[str, Any]] | None = None
_BASE_HISTORY_CSV: Callable[..., bytes] | None = None
_BASE_MATERIALIZE_UPDATES: Callable[..., list[dict[str, Any]]] | None = None

_TERMINAL_ADDITION_STATES = {
    "error": "Erro",
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


def _resolve_reference_file(expected: Path) -> Path | None:
    """Aceita diferenças de caixa/nome sem transformar a referência em requisito fatal."""
    expected = Path(expected)
    if expected.is_file():
        return expected

    directory = expected.parent
    if not directory.is_dir():
        return None

    wanted = expected.name.casefold()
    aliases = {wanted}
    if "plugin" in wanted:
        aliases.update({"exemplo plugin.webp", "exemplo-plugin.webp", "exemplo_plugin.webp"})
    if "tema" in wanted or "theme" in wanted:
        aliases.update({"exemplo tema.webp", "exemplo-tema.webp", "exemplo_tema.webp"})

    for candidate in directory.iterdir():
        if candidate.is_file() and candidate.name.casefold() in aliases:
            return candidate
    return None


def _reference_path_resilient(job: Mapping[str, Any]) -> Path:
    if _BASE_REFERENCE_PATH is None:
        raise RuntimeError("Resolvedor base de referência visual indisponível")
    expected = Path(_BASE_REFERENCE_PATH(job))
    return _resolve_reference_file(expected) or expected


def _attach_reference_resilient(page: Any, reference_path: Path, job_id: str) -> bool:
    """A ausência do mockup não pode abortar toda a Preparação.

    O prompt já contém as regras de composição. Quando a referência local existe,
    ela continua sendo anexada normalmente; quando não existe ou o upload falha,
    a geração segue sem o arquivo e registra um aviso observável.
    """
    resolved = _resolve_reference_file(Path(reference_path))
    if resolved is None:
        addition_ui._persistent_emit(
            job_id,
            "Referência visual local não encontrada; continuando a geração da imagem sem o mockup de referência.",
            step="chatgpt_image",
        )
        return True

    if _BASE_ATTACH_REFERENCE is None:
        return True

    try:
        attached = bool(_BASE_ATTACH_REFERENCE(page, resolved, job_id))
    except Exception as error:
        addition_ui._persistent_emit(
            job_id,
            f"Não foi possível anexar a referência visual ({_clean(error)}); continuando sem o anexo.",
            step="chatgpt_image",
        )
        return True

    if not attached:
        addition_ui._persistent_emit(
            job_id,
            "O anexo da referência visual não foi confirmado; continuando a geração com as instruções do prompt.",
            step="chatgpt_image",
        )
    return True


def _addition_terminal_error(row: Mapping[str, Any]) -> str:
    return (
        _clean(row.get("operation_error"))
        or _clean(row.get("error"))
        or _clean(row.get("status_message"))
    )


def _backfill_terminal_addition_history() -> int:
    """Reconcilia Erro/Interrompido/Cancelado do job com o histórico por tentativa."""
    addition_ui._ensure_schema()
    inserted = 0

    with additions._db() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM addition_jobs "
                "WHERE queue_state IN ('error','interrupted','canceled') "
                "ORDER BY updated_at, created_at"
            ).fetchall()
        ]

        for row in rows:
            job_id = _clean(row.get("job_id"))
            status = _clean(row.get("queue_state"))
            if not job_id or status not in _TERMINAL_ADDITION_STATES:
                continue

            error_text = _addition_terminal_error(row)
            duplicate = connection.execute(
                "SELECT 1 FROM addition_attempt_history "
                "WHERE job_id=? AND status=? AND COALESCE(error,'')=? "
                "ORDER BY attempt_id DESC LIMIT 1",
                (job_id, status, error_text),
            ).fetchone()
            if duplicate is not None:
                continue

            previous = connection.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) AS attempt_no "
                "FROM addition_attempt_history WHERE job_id=?",
                (job_id,),
            ).fetchone()
            previous_no = _safe_int(previous["attempt_no"] if previous else 0)
            attempt_no = max(previous_no + 1, _safe_int(row.get("attempts"), 0), 1)
            started_at = (
                _clean(row.get("started_at"))
                or _clean(row.get("created_at"))
                or _clean(row.get("updated_at"))
            )
            finished_at = (
                _clean(row.get("finished_at"))
                or _clean(row.get("updated_at"))
                or started_at
            )
            current_step = _clean(row.get("current_step")) or status
            progress = max(0, min(100, _safe_int(row.get("progress"), 0)))
            logs = addition_ui._dump_logs(addition_ui._load_logs(row.get("execution_logs")))
            result = _TERMINAL_ADDITION_STATES[status]
            if status == "error" and current_step in {"error", "chatgpt_image", "starting"}:
                result = "Erro na preparação"

            connection.execute(
                """
                INSERT INTO addition_attempt_history (
                    job_id, attempt_no, status, result, final_state, current_step,
                    progress, error, logs, source_name, source_version,
                    source_product_url, source_official_url, desenvolvedor,
                    site_oficial, kind, category_name, woo_product_id,
                    started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    attempt_no,
                    status,
                    result,
                    status,
                    current_step,
                    progress,
                    error_text,
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


def _history_page_reliable(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _backfill_terminal_addition_history()
    if _BASE_HISTORY_PAGE is None:
        return {}
    return _BASE_HISTORY_PAGE(*args, **kwargs)


def _history_csv_reliable(*args: Any, **kwargs: Any) -> bytes:
    _backfill_terminal_addition_history()
    if _BASE_HISTORY_CSV is None:
        return b""
    return _BASE_HISTORY_CSV(*args, **kwargs)


def _materialize_updates_with_queue(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Nunca deixa itens queued/executing sumirem do payload usado pela UI."""
    base_rows = list((_BASE_MATERIALIZE_UPDATES(*args, **kwargs) if _BASE_MATERIALIZE_UPDATES else []) or [])
    by_id = {
        _clean(row.get("job_id")): dict(row)
        for row in base_rows
        if isinstance(row, Mapping) and _clean(row.get("job_id"))
    }
    try:
        snapshot = update_runtime.queue_snapshot()
    except Exception:
        snapshot = {}

    for key in ("queued", "executing"):
        for row in snapshot.get(key, []) or []:
            if not isinstance(row, Mapping):
                continue
            job_id = _clean(row.get("job_id"))
            if job_id:
                by_id[job_id] = {**by_id.get(job_id, {}), **dict(row)}

    return list(by_id.values())


def install_operational_reliability_policy() -> None:
    global _INSTALLED
    global _BASE_REFERENCE_PATH, _BASE_ATTACH_REFERENCE
    global _BASE_HISTORY_PAGE, _BASE_HISTORY_CSV, _BASE_MATERIALIZE_UPDATES

    if _INSTALLED:
        return

    _BASE_REFERENCE_PATH = creative._reference_path
    _BASE_ATTACH_REFERENCE = creative._attach_reference
    creative._reference_path = _reference_path_resilient
    creative._attach_reference = _attach_reference_resilient

    _backfill_terminal_addition_history()
    _BASE_HISTORY_PAGE = addition_ui._history_page
    _BASE_HISTORY_CSV = addition_ui._history_csv
    addition_ui._history_page = _history_page_reliable
    addition_ui._history_csv = _history_csv_reliable

    _BASE_MATERIALIZE_UPDATES = web.materialize_update_jobs
    web.materialize_update_jobs = _materialize_updates_with_queue

    _INSTALLED = True
