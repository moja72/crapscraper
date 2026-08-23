from __future__ import annotations

from typing import Any, Callable, Mapping

import app.addition_operational_ui_policy as additions_ui

_INSTALLED = False
_BASE_PREPARE_ONE: Callable[[str, Any], None] | None = None
_BASE_HAS_PENDING_PIPELINE: Callable[[], bool] | None = None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _prepared_for_queue(row: Mapping[str, Any]) -> bool:
    """Um item só entra na fila depois de terminar a Preparação."""
    queue_state = _clean(row.get("queue_state"))
    internal_state = _clean(row.get("state"))
    return bool(
        queue_state == "ready"
        or additions_ui._prepared_local(row)
        or internal_state in {"ready_to_create", "draft_created", "published"}
    )


def _prepare_one(job_id: str, manager: Any) -> None:
    """Prepara normalmente; retry explícito pode seguir até fila/execução."""
    if _BASE_PREPARE_ONE is None:
        raise RuntimeError("Preparador base de adições indisponível")

    row_before = additions_ui._job_snapshot(job_id)
    auto_enqueue_requested = bool(_safe_int(row_before.get("enqueue_after_prepare")))

    # Preparações normais continuam manuais: Preparação -> Pronto -> Adicionar à fila.
    # A única exceção é Tentar novamente, que marca enqueue_after_prepare=1 para
    # refazer o fluxo quebrado e seguir automaticamente até a execução.
    if not auto_enqueue_requested:
        additions_ui._update_operation(job_id, enqueue_after_prepare=0)

    _BASE_PREPARE_ONE(job_id, manager)

    # Defesa contra estado legado somente no fluxo manual. No retry explícito,
    # preservar queued é necessário para o worker concluir o cadastro.
    row_after = additions_ui._job_snapshot(job_id)
    if not auto_enqueue_requested and _clean(row_after.get("queue_state")) == "queued":
        additions_ui._update_operation(
            job_id,
            queue_state="ready",
            queue_position=0,
            enqueue_after_prepare=0,
            status_message="Preparação concluída; pronta para entrar na fila",
        )
        additions_ui._renumber_queue()


def _request_add(payload: Mapping[str, Any], manager: Any, *, retry: bool = False) -> dict[str, Any]:
    """Fila manual no uso normal; retry explícito retoma o fluxo até concluir."""
    job_ids = additions_ui._normalize_job_ids(payload)
    queued = 0
    preparing = 0
    skipped = 0
    not_ready = 0

    for job_id in job_ids:
        row = additions_ui._job_snapshot(job_id)
        state = _clean(row.get("queue_state"))

        if not bool(_safe_int(row.get("approval_active"), 1)):
            skipped += 1
            continue
        if state in {"preparing", "queued", "executing", "completed"}:
            skipped += 1
            continue
        if _safe_int(row.get("active_attempt_id")):
            skipped += 1
            continue

        if _prepared_for_queue(row):
            additions_ui._enqueue_ready(job_id)
            queued += 1
            continue

        # Tentar novamente é uma intenção explícita de retomar uma operação que
        # falhou. Cria nova tentativa, refaz a Preparação e, quando ela terminar,
        # promove o item para queued para o worker concluir o cadastro.
        if retry and state in {"error", "interrupted"}:
            additions_ui._create_attempt(job_id)
            additions_ui._update_operation(
                job_id,
                queue_state="preparing",
                queue_position=0,
                enqueue_after_prepare=1,
                current_step="starting",
                progress=0,
                status_message="Nova tentativa iniciada; preparando para concluir o cadastro",
                operation_error="",
                hidden_from_queue=0,
                finished_at="",
            )
            preparing += 1
            continue

        not_ready += 1

    accepted = queued + preparing
    skipped += not_ready

    # No fluxo normal, Adicionar à fila continua apenas enfileirando. Já em
    # Tentar novamente, a própria ação deve efetivamente retomar o cadastro.
    if retry and accepted:
        additions_ui._set_queue_runtime("running")
    if preparing:
        additions_ui._start_preparation_worker(manager)
    if retry and accepted:
        additions_ui._start_queue_worker()

    if retry:
        message = (
            f"{queued} produto(s) retomado(s) diretamente na fila; "
            f"{preparing} reenviado(s) à preparação e execução; {skipped} ignorado(s)."
        )
    else:
        message = f"{queued} produto(s) adicionado(s) à fila."
        if not_ready:
            message += f" {not_ready} ainda precisam concluir a Preparação."
        if skipped - not_ready:
            message += f" {skipped - not_ready} já estavam ocupados ou concluídos."

    return {
        "ok": True,
        "message": message,
        "accepted": accepted,
        "queued": queued,
        "preparing": preparing,
        "not_ready": not_ready,
        "skipped": skipped,
        "queue": additions_ui._queue_runtime(),
    }


def _start_queue() -> dict[str, Any]:
    """Executa apenas o que já foi explicitamente colocado na fila."""
    additions_ui._renumber_queue()
    with additions_ui.additions._db() as connection:
        queued = _safe_int(connection.execute(
            "SELECT COUNT(*) AS total FROM addition_jobs "
            "WHERE approval_active=1 AND queue_state='queued'"
        ).fetchone()["total"])
        executing = _safe_int(connection.execute(
            "SELECT COUNT(*) AS total FROM addition_jobs "
            "WHERE approval_active=1 AND queue_state='executing'"
        ).fetchone()["total"])

    if queued <= 0 and executing <= 0:
        runtime = additions_ui._set_queue_runtime("stopped")
        return {
            "ok": True,
            "message": "Nenhum produto está na fila. Prepare os itens e use Adicionar à fila antes de executar.",
            "started": False,
            "queue": runtime,
        }

    additions_ui._set_queue_runtime("running")
    started = additions_ui._start_queue_worker()
    return {
        "ok": True,
        "message": f"Fila de adições iniciada com {queued} item(ns) aguardando execução.",
        "started": started,
        "queue": additions_ui._queue_runtime(),
    }


def _has_pending_auto_pipeline() -> bool:
    """Mantém o worker vivo enquanto um retry ainda está em Preparação."""
    if _BASE_HAS_PENDING_PIPELINE is not None:
        try:
            return bool(_BASE_HAS_PENDING_PIPELINE())
        except Exception:
            pass

    with additions_ui.additions._db() as connection:
        row = connection.execute(
            "SELECT 1 FROM addition_jobs WHERE approval_active=1 "
            "AND queue_state='preparing' AND enqueue_after_prepare=1 LIMIT 1"
        ).fetchone()
    return row is not None


def install_preparation_execution_gate_policy() -> None:
    global _INSTALLED, _BASE_PREPARE_ONE, _BASE_HAS_PENDING_PIPELINE
    if _INSTALLED:
        return

    # Neutraliza somente flags antigas no boot. Novos retries explícitos podem
    # usar enqueue_after_prepare=1 durante a própria tentativa.
    additions_ui._ensure_schema()
    with additions_ui.additions._db() as connection:
        connection.execute(
            "UPDATE addition_jobs SET enqueue_after_prepare=0 "
            "WHERE enqueue_after_prepare<>0"
        )

    _BASE_PREPARE_ONE = additions_ui._prepare_one
    _BASE_HAS_PENDING_PIPELINE = additions_ui._has_pending_pipeline_preparation
    additions_ui._prepare_one = _prepare_one
    additions_ui._request_add = _request_add
    additions_ui._start_queue = _start_queue
    additions_ui._has_pending_pipeline_preparation = _has_pending_auto_pipeline
    _INSTALLED = True
