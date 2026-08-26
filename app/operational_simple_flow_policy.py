from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app import settings
from app.configuration import missing_for
from app.integrations.wordpress import sanitize_text
from app.operations.execution_plan import build_execution_plan
from app.operations.models import JobState
import app.addition_one_click_policy as addition_one_click
import app.new_product_workflow_policy as additions
import app.operations.runtime as runtime
import app.web as web


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "operational_simple_flow.js"
_BATCH_LOCK = threading.RLock()


def _empty_batch(kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "running": False,
        "done": False,
        "total": 0,
        "processed": 0,
        "success": 0,
        "errors": 0,
        "current_job_id": "",
        "message": "Pronto.",
        "last_error": "",
        "results": [],
        "started_at": "",
        "finished_at": "",
    }


_BATCHES: dict[str, dict[str, Any]] = {
    "update": _empty_batch("update"),
    "addition": _empty_batch("addition"),
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_job_ids(payload: Mapping[str, Any] | None) -> list[str]:
    data = dict(payload or {})
    raw: Any = data.get("job_ids")
    if raw in (None, ""):
        raw = [data.get("job_id")]
    elif isinstance(raw, str):
        raw = [raw]

    if not isinstance(raw, Iterable) or isinstance(raw, (bytes, bytearray, Mapping)):
        raise ValueError("Informe ao menos um item para executar.")

    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        job_id = str(value or "").strip()
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        result.append(job_id)

    if not result:
        raise ValueError("Selecione ao menos um produto.")
    if len(result) > 250:
        raise ValueError("Execute no máximo 250 produtos por lote.")
    return result


def _batch_public(kind: str) -> dict[str, Any]:
    with _BATCH_LOCK:
        batch = deepcopy(_BATCHES[kind])
        batch["results"] = list(batch.get("results") or [])[-40:]
        return batch


def _set_batch(kind: str, **values: Any) -> dict[str, Any]:
    with _BATCH_LOCK:
        _BATCHES[kind].update(values)
        return deepcopy(_BATCHES[kind])


def _append_batch_result(kind: str, result: Mapping[str, Any]) -> None:
    with _BATCH_LOCK:
        rows = list(_BATCHES[kind].get("results") or [])
        rows.append(dict(result))
        _BATCHES[kind]["results"] = rows[-100:]


def _existing_update_artifacts(job: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        preview = runtime.get_preview(job.job_id)
        plan = runtime.get_plan(job.job_id)
    except (KeyError, ValueError):
        return None, None
    return preview, plan


def _prepare_update(job: Any, manager: Any, logger: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    missing = missing_for("prepare")
    if missing:
        raise RuntimeError(
            "Pré-requisitos ausentes para a atualização automática: "
            + ", ".join(missing)
            + ". Nenhum download foi iniciado."
        )

    primary = web._get_primary_app(manager)
    logger.clear()
    factory = getattr(primary, "update_preparation_service_factory", None)
    service = factory() if callable(factory) else web._build_update_preparation_service(primary, logger.log)
    preview = service.prepare(job).to_dict()
    preview["update_logs"] = logger.to_list()

    # Passa pela função exposta em web porque as policies de confiabilidade da
    # main a envolvem para reconciliar snapshots e materializar o plano seguro.
    preview = web.save_preview(job.job_id, preview)
    if preview.get("ready") is not True:
        raise RuntimeError("A preparação terminou sem liberar o produto para atualização.")

    try:
        plan = runtime.get_plan(job.job_id)
    except (KeyError, ValueError):
        # Fallback defensivo caso a policy de plano automático seja desativada.
        plan = build_execution_plan(job, preview, logger=logger.log)
        plan["update_logs"] = logger.to_list()
        runtime.save_plan(job.job_id, plan)
        runtime.persist_job(job)
    # A geração automática já validou identidade, vínculo, ZIP atual, ZIP novo e
    # rollback. Preserve o invariante do gate: plano ready implica job plan_ready.
    # Isso não torna nenhum job elegível por si só; is_execution_eligible ainda
    # revalida todos os predicados e a existência do artefato local.
    if _reconcile_ready_plan_state(job, preview, plan):
        runtime.persist_job(job)
    return preview, plan


def _reconcile_ready_plan_state(job: Any, preview: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Restore the persisted job invariant without weakening execution eligibility."""
    if not (
        preview.get("ready") is True
        and plan.get("ready") is True
        and str(plan.get("job_id") or "") == str(job.job_id)
        and int(plan.get("woo_product_id") or 0) == int(job.woo_product_id)
        and job.state == JobState.PREPARED
    ):
        return False
    job.set_state(JobState.PLAN_READY, "Estado reconciliado com o plano validado")
    return True


def _execute_update_one(job_id: str, manager: Any) -> dict[str, Any]:
    job = runtime.get_job(job_id)
    if job.state == JobState.COMPLETED:
        return {"job_id": job_id, "ok": True, "status": "completed", "message": "Atualização já concluída."}
    if job.state == JobState.EXECUTING:
        raise RuntimeError("Este produto já está sendo atualizado.")
    if job.state == JobState.QUEUED:
        raise RuntimeError("Este produto já está na fila avançada. Pause/remova-o da fila antes de usar o fluxo simplificado.")

    logger = web._UPDATE_LOGS.for_job(job.job_id)
    operation_lock = None
    with web._UPDATE_WORKERS_LOCK:
        operation_lock = web._UPDATE_JOB_LOCKS.setdefault(job.job_id, threading.Lock())
    if not operation_lock.acquire(blocking=False):
        raise RuntimeError("Outro processo deste produto já está em andamento.")

    try:
        preview, plan = _existing_update_artifacts(job)
        eligible = bool(
            preview
            and plan
            and runtime.is_execution_eligible(
                job,
                preview,
                plan,
                enabled=settings.UPDATE_EXECUTION_ENABLED,
                allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
            )
        )

        if not eligible:
            preview, plan = _prepare_update(job, manager, logger)

        if not runtime.is_execution_eligible(
            job,
            preview,
            plan,
            enabled=settings.UPDATE_EXECUTION_ENABLED,
            allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
        ):
            raise RuntimeError(
                "O produto foi preparado, mas a execução real não está habilitada ou alguma pré-condição deixou de ser válida."
            )

        job.attempts += 1
        logger.clear()
        executor = web._build_controlled_update_executor(job, logger.log)
        executor.execute(job, plan, f"EXECUTAR {job.woo_product_id}")
        return {
            "job_id": job_id,
            "ok": True,
            "status": job.state.value,
            "message": "Atualização concluída." if job.state == JobState.COMPLETED else "Atualização executada.",
        }
    except Exception as error:
        if job.state == JobState.EXECUTING:
            job.set_state(JobState.ERROR, "Falha técnica durante o fluxo simplificado")
        safe_error = logger.sanitize(error)
        if not job.execution_error:
            job.execution_error = safe_error
        logger.log(f"Falha no fluxo simplificado: {safe_error}")
        raise RuntimeError(safe_error) from None
    finally:
        job.execution_logs = logger.to_list()
        runtime.persist_job(job)
        operation_lock.release()


def _execute_addition_one(job_id: str, manager: Any) -> dict[str, Any]:
    additions._row(job_id)
    with addition_one_click._TASK_LOCK:
        current = addition_one_click._task(job_id)
        if current.get("running"):
            raise RuntimeError("Este produto já está sendo adicionado.")

    addition_one_click._run(job_id, manager)
    task = addition_one_click._public_task(job_id)
    if task.get("error"):
        raise RuntimeError(str(task.get("error") or "Falha no cadastro automático."))
    if not task.get("done"):
        raise RuntimeError("O cadastro automático terminou sem confirmação de conclusão.")
    return {
        "job_id": job_id,
        "ok": True,
        "status": "completed",
        "message": "Produto adicionado e validado.",
    }


def _run_batch(kind: str, job_ids: list[str], manager: Any) -> None:
    runner = _execute_update_one if kind == "update" else _execute_addition_one
    total = len(job_ids)
    for index, job_id in enumerate(job_ids, start=1):
        _set_batch(
            kind,
            current_job_id=job_id,
            message=("Atualizando" if kind == "update" else "Adicionando") + f" {index} de {total}…",
        )
        try:
            result = runner(job_id, manager)
            _append_batch_result(kind, result)
            with _BATCH_LOCK:
                _BATCHES[kind]["success"] += 1
        except Exception as error:
            message = sanitize_text(error)
            _append_batch_result(
                kind,
                {"job_id": job_id, "ok": False, "status": "error", "message": message},
            )
            with _BATCH_LOCK:
                _BATCHES[kind]["errors"] += 1
                _BATCHES[kind]["last_error"] = message
        finally:
            with _BATCH_LOCK:
                _BATCHES[kind]["processed"] += 1

    batch = _batch_public(kind)
    errors = int(batch.get("errors") or 0)
    success = int(batch.get("success") or 0)
    message = f"{success} concluído(s)"
    if errors:
        message += f" · {errors} com erro"
    _set_batch(
        kind,
        running=False,
        done=True,
        current_job_id="",
        message=message,
        finished_at=_now_iso(),
    )


def _start_batch(kind: str, job_ids: list[str], manager: Any) -> dict[str, Any]:
    if kind == "update" and not settings.UPDATE_EXECUTION_ENABLED:
        raise ValueError(
            "A execução real de atualizações está desabilitada. "
            "Defina SCRAPER_UPDATE_EXECUTION_ENABLED=1 e reinicie o CrapScraper antes de usar Executar selecionados."
        )

    with _BATCH_LOCK:
        if _BATCHES[kind].get("running"):
            label = "atualização" if kind == "update" else "adição"
            raise ValueError(f"Já existe um lote de {label} em andamento.")
        _BATCHES[kind] = {
            **_empty_batch(kind),
            "running": True,
            "total": len(job_ids),
            "message": "Iniciando…",
            "started_at": _now_iso(),
        }

    threading.Thread(
        target=_run_batch,
        args=(kind, list(job_ids), manager),
        name=f"simple-{kind}-batch",
        daemon=True,
    ).start()
    return _batch_public(kind)


def _script_block() -> str:
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-operational-simple-flow>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = additions._manager_from_handler(handler_class)

    class OperationalSimpleFlowHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/operacoes/simples/status":
                self._send_json(
                    {
                        "ok": True,
                        "update": _batch_public("update"),
                        "addition": _batch_public("addition"),
                    }
                )
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path not in {"/operacoes/simples/atualizar", "/operacoes/simples/adicionar"}:
                return super().do_POST()
            try:
                payload = self._read_json_body()
                job_ids = _normalize_job_ids(payload)
                kind = "update" if path.endswith("/atualizar") else "addition"
                batch = _start_batch(kind, job_ids, manager)
                self._send_json(
                    {
                        "ok": True,
                        "message": "Fluxo automático iniciado.",
                        "batch": batch,
                    }
                )
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, OperationalSimpleFlowHandler, *args, **kwargs)


def install_operational_simple_flow_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
