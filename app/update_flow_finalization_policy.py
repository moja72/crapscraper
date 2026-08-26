from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from app import settings
from app.integrations.download_validation import diagnostic_message
from app.integrations.ssh_storage import ReadOnlySSHStorage
from app.integrations.update_download import build_canonical_source_downloader
from app.integrations.update_session import get_authenticated_update_session
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.woocommerce import WooCommerceClient
from app.integrations.wordpress import sanitize_text
from app.operations.models import JobState
from app.operations.preparation import UpdatePreparationService
from app.update_error_model import normalize_update_error
import app.operational_history_shared_policy as history_shared
import app.operational_simple_flow_policy as simple_flow
import app.operations.runtime as runtime
import app.update_queue_execution_reliability_policy as queue_reliability
import app.update_recoverability_policy as recoverability
import app.web as web


_INSTALLED = False
_BASE_JOB_PUBLIC: Callable[..., dict[str, Any]] | None = None
_BASE_HISTORY_ROWS: Callable[..., list[dict[str, Any]]] | None = None
_BASE_COMBINED_LOGS: Callable[..., list[str]] | None = None
_BASE_RECOVERY_REUSE: Callable[..., Any] | None = None
_BASE_RECOVERY_MAKE: Callable[..., Any] | None = None
_BASE_SIMPLE_BATCH: Callable[..., Any] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_flow_final.js"
_FINAL_DOWNLOAD_STAGES = {
    "final_download",
    "intermediate_download_target",
    "plugintheme_final_download",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _build_canonical_preparation_service(app: Any, logger: Any = None) -> UpdatePreparationService:
    """Factory única: individual e lote recebem os mesmos adapters e sessão validada."""
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    key = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    secret = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    if not all((base, key, secret)):
        raise RuntimeError(
            "Configure SCRAPER_WP_BASE_URL/SCRAPER_WC_CONSUMER_KEY/"
            "SCRAPER_WC_CONSUMER_SECRET para preparar o job."
        )

    log = logger if callable(logger) else (lambda _message: None)
    storage = ReadOnlySSHStorage.from_env().connect()
    downloader = build_canonical_source_downloader(
        getattr(app, "ultrapack_http_session", None),
        getattr(app, "plugintheme_http_session", None),
    )

    def session_provider(job: Any) -> Any:
        return get_authenticated_update_session(
            app,
            str(getattr(job, "ultrapack_url", "") or ""),
            downloader,
            logger=log,
        )

    def helper_probe() -> bool:
        client = getattr(storage, "_client", None)
        if client is None:
            return False
        try:
            _stdin, stdout, _stderr = client.exec_command(
                "test -x /usr/local/sbin/crapscraper-zip-helper",
                timeout=15,
            )
            return int(stdout.channel.recv_exit_status()) == 0
        except Exception:
            return False

    return UpdatePreparationService(
        WooCommerceClient(base, key, secret),
        storage,
        downloader,
        staging_root=settings.DATA_DIR / "staging" / "updates",
        helper_probe=helper_probe,
        session_provider=session_provider,
        logger=log,
    )


def _local_retry_artifact(
    service: UpdatePreparationService,
    *,
    target_version: str,
    previous_path: str,
    previous_sha: str,
    previous_version: str,
) -> tuple[dict[str, Any], str] | None:
    if not previous_path or not previous_sha or not previous_version:
        return None
    same = recoverability._same_version(previous_version, target_version)
    candidate = Path(previous_path)
    if not same or not candidate.is_file():
        return None
    try:
        artifact = UltrapackDownloader.validate_zip(candidate, source_url="retry-local-reuse")
    except Exception as error:
        service.logger(f"⚠ ZIP local anterior não pôde ser reaproveitado: {sanitize_text(error)}")
        return None
    if artifact.sha256.lower() != previous_sha.lower():
        service.logger("⚠ ZIP local anterior ignorado: SHA-256 diverge do artefato persistido")
        return None
    service.logger(
        f"♻ Reaproveitando ZIP local já validado: {candidate.name} · SHA-256 {artifact.sha256[:12]}…"
    )
    return artifact.to_dict(), target_version


def _recovery_reuse_without_duplicate_network(
    service: UpdatePreparationService,
    job: Any,
    *,
    target_version: str,
    previous_path: str,
    previous_sha: str,
    previous_version: str,
) -> tuple[dict[str, Any], str]:
    local = _local_retry_artifact(
        service,
        target_version=target_version,
        previous_path=previous_path,
        previous_sha=previous_sha,
        previous_version=previous_version,
    )
    if local is not None:
        return local

    trace = list(getattr(service.downloader, "request_trace", None) or [])
    attempted = any(_clean(item.get("stage")) in _FINAL_DOWNLOAD_STAGES for item in trace if isinstance(item, Mapping))
    if attempted:
        raise RuntimeError(
            "O download já falhou nesta tentativa e a mesma estratégia não será repetida automaticamente. "
            "A próxima tentativa revalidará sessão, URL e produto antes de solicitar um novo arquivo."
        )
    if _BASE_RECOVERY_REUSE is None:
        raise RuntimeError("Recuperação de ZIP indisponível")
    # Nenhuma requisição final ocorreu no prepare base (por exemplo, snapshot antigo
    # corrigido pela policy de drift). Nesse caso há uma única tentativa legítima.
    return _BASE_RECOVERY_REUSE(
        service,
        job,
        target_version=target_version,
        previous_path=previous_path,
        previous_sha=previous_sha,
        previous_version=previous_version,
    )


def _recovery_make_with_diagnostic(service: UpdatePreparationService, job: Any, preview: Any, **kwargs: Any) -> Any:
    if _BASE_RECOVERY_MAKE is None:
        return preview
    result = _BASE_RECOVERY_MAKE(service, job, preview, **kwargs)
    diagnostic = dict(getattr(service.downloader, "last_download_diagnostic", None) or {})
    if not diagnostic:
        return result

    fresh = dict(getattr(result, "new_zip", None) or {})
    if fresh.get("sha256"):
        return result

    message = diagnostic_message(diagnostic)
    fresh["error"] = message
    fresh["download_diagnostic"] = diagnostic
    result.new_zip = fresh
    for item in getattr(result, "validations", []) or []:
        if _clean(getattr(item, "key", "")) in {"downloaded", "new_zip"}:
            item.ok = False
            item.level = "error"
            item.detail = message
    job.execution_error = message
    if job.state not in {JobState.ERROR, JobState.FAILED, JobState.ROLLBACK_REQUIRED}:
        job.set_state(JobState.BLOCKED, "Download inválido; nova tentativa permanece disponível")
    result.state = job.state.value
    return result


def _execution_artifacts(job: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return runtime.get_preview(job.job_id), runtime.get_plan(job.job_id)
    except (KeyError, ValueError):
        return None, None


def _claimed_plan_valid(job: Any, preview: Mapping[str, Any] | None, plan: Mapping[str, Any] | None) -> bool:
    candidate = dict(plan or {})
    return bool(
        (preview or {}).get("ready") is True
        and candidate.get("ready") is True
        and _clean(candidate.get("job_id")) == _clean(job.job_id)
        and int(candidate.get("woo_product_id") or 0) == int(job.woo_product_id)
        and job.relationship in runtime.SAFE_EXECUTION_RELATIONSHIPS
        and _clean((candidate.get("new_zip") or {}).get("local_staging_path"))
        and Path(_clean((candidate.get("new_zip") or {}).get("local_staging_path"))).is_file()
    )


def execute_update_job(job_id: str, manager: Any, *, claimed_job: Any = None) -> dict[str, Any]:
    """Executor canônico usado por clique individual, lote simplificado e fila avançada."""
    job = claimed_job or runtime.get_job(job_id)
    if job.state == JobState.COMPLETED:
        return {"job_id": job_id, "ok": True, "status": "completed", "message": "Atualização já concluída."}
    if claimed_job is None and job.state == JobState.EXECUTING:
        raise RuntimeError("Este produto já está sendo atualizado.")
    if claimed_job is None and job.state == JobState.QUEUED:
        raise RuntimeError("Este produto já está na fila ativa.")

    logger = web._UPDATE_LOGS.for_job(job.job_id)
    with web._UPDATE_WORKERS_LOCK:
        operation_lock = web._UPDATE_JOB_LOCKS.setdefault(job.job_id, threading.Lock())
    if not operation_lock.acquire(blocking=False):
        raise RuntimeError("Outro processo deste produto já está em andamento.")

    try:
        preview, plan = _execution_artifacts(job)
        if claimed_job is None:
            eligible = bool(
                preview and plan and runtime.is_execution_eligible(
                    job,
                    preview,
                    plan,
                    enabled=settings.UPDATE_EXECUTION_ENABLED,
                    allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
                )
            )
            if not eligible:
                preview, plan = simple_flow._prepare_update(job, manager, logger)
            if not runtime.is_execution_eligible(
                job,
                preview,
                plan,
                enabled=settings.UPDATE_EXECUTION_ENABLED,
                allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
            ):
                raise RuntimeError(
                    "O produto foi preparado, mas alguma pré-condição de execução deixou de ser válida."
                )
            job.attempts += 1
        elif not _claimed_plan_valid(job, preview, plan):
            raise RuntimeError("O job reservado pela fila perdeu as pré-condições do plano antes da execução.")

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
            job.set_state(JobState.ERROR, "Falha técnica durante a atualização")
        safe_error = logger.sanitize(error)
        if not job.execution_error:
            job.execution_error = safe_error
        logger.log(f"❌ {safe_error}")
        raise RuntimeError(safe_error) from None
    finally:
        job.execution_logs = logger.to_list()
        runtime.persist_job(job)
        operation_lock.release()


def _run_batch_canonical(kind: str, job_ids: list[str], manager: Any) -> None:
    if kind != "update":
        if _BASE_SIMPLE_BATCH is not None:
            return _BASE_SIMPLE_BATCH(kind, job_ids, manager)
        return

    total = len(job_ids)
    paused = False
    for index, job_id in enumerate(job_ids, start=1):
        simple_flow._set_batch(
            kind,
            current_job_id=job_id,
            message=f"Atualizando {index} de {total}…",
        )
        try:
            result = execute_update_job(job_id, manager)
            simple_flow._append_batch_result(kind, result)
            with simple_flow._BATCH_LOCK:
                simple_flow._BATCHES[kind]["success"] += 1
        except Exception as error:
            message = sanitize_text(error)
            try:
                job = runtime.get_job(job_id)
                normalized = normalize_update_error(job, runtime._PREVIEWS.get(job_id), runtime._PLANS.get(job_id))
            except Exception:
                normalized = {"display_text": message, "global_block": False}
            display = _clean(normalized.get("display_text")) or message
            simple_flow._append_batch_result(
                kind,
                {"job_id": job_id, "ok": False, "status": "error", "message": display,
                 "normalized_error": normalized},
            )
            with simple_flow._BATCH_LOCK:
                simple_flow._BATCHES[kind]["errors"] += 1
                simple_flow._BATCHES[kind]["last_error"] = display
            if bool(normalized.get("global_block")):
                paused = True
        finally:
            with simple_flow._BATCH_LOCK:
                simple_flow._BATCHES[kind]["processed"] += 1
        if paused:
            break

    batch = simple_flow._batch_public(kind)
    errors = int(batch.get("errors") or 0)
    success = int(batch.get("success") or 0)
    if paused:
        message = (
            f"Processamento pausado por condição global da fonte · {success} concluído(s) · {errors} com erro. "
            "Os itens restantes não foram alterados."
        )
        simple_flow._set_batch(
            kind,
            running=False,
            done=False,
            paused=True,
            global_block=True,
            current_job_id="",
            message=message,
            finished_at=simple_flow._now_iso(),
        )
        return

    message = f"{success} concluído(s)"
    if errors:
        message += f" · {errors} com erro"
    simple_flow._set_batch(
        kind,
        running=False,
        done=True,
        paused=False,
        global_block=False,
        current_job_id="",
        message=message,
        finished_at=simple_flow._now_iso(),
    )


def _run_advanced_queue_canonical() -> None:
    """Fila avançada é apenas orquestração; a execução é a mesma função do individual."""
    while True:
        job = queue_reliability._claim_next_queued_job()
        if job is None:
            snapshot = runtime.queue_snapshot()
            if snapshot["status"] == "running" and not snapshot["queued"]:
                runtime.set_queue_status("stopped")
            return
        try:
            execute_update_job(job.job_id, None, claimed_job=job)
        except Exception:
            try:
                normalized = normalize_update_error(job, runtime._PREVIEWS.get(job.job_id), runtime._PLANS.get(job.job_id))
            except Exception:
                normalized = {}
            if normalized.get("global_block"):
                runtime.set_queue_status("paused")
                return
        finally:
            job.queue_position = 0
            runtime.persist_job(job)


def _public_job(job: Any) -> dict[str, Any]:
    if _BASE_JOB_PUBLIC is None:
        return {}
    data = _BASE_JOB_PUBLIC(job)
    preview = runtime._PREVIEWS.get(job.job_id)
    plan = runtime._PLANS.get(job.job_id)
    normalized = normalize_update_error(job, preview, plan)
    data["normalized_error"] = normalized
    data["execution_error_raw"] = data.get("execution_error", "")
    if normalized.get("has_error"):
        data["execution_error"] = normalized.get("display_text") or normalized.get("message") or data.get("execution_error", "")
    return data


def _history_rows() -> list[dict[str, Any]]:
    rows = _BASE_HISTORY_ROWS() if _BASE_HISTORY_ROWS is not None else []
    for row in rows:
        job_id = _clean(row.get("job_id"))
        try:
            job = runtime.get_job(job_id)
        except Exception:
            continue
        normalized = normalize_update_error(job, runtime._PREVIEWS.get(job_id), runtime._PLANS.get(job_id))
        row["normalized_error"] = normalized
        if normalized.get("has_error"):
            display = normalized.get("display_text") or normalized.get("message") or ""
            row["error"] = display
            row["result"] = display
    return rows


def _combined_logs(job_id: str) -> list[str]:
    lines = _BASE_COMBINED_LOGS(job_id) if _BASE_COMBINED_LOGS is not None else []
    try:
        job = runtime.get_job(job_id)
        normalized = normalize_update_error(job, runtime._PREVIEWS.get(job_id), runtime._PLANS.get(job_id))
    except Exception:
        return lines
    current_error = _clean(normalized.get("current_error")).lower()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        text = str(raw or "").strip()
        compact = _clean(text)
        lower = compact.lower()
        if not compact:
            continue
        if lower.startswith("[erro atual]") or lower.startswith("[diagnóstico]"):
            continue
        if current_error and current_error in lower and (
            "falha no fluxo simplificado" in lower
            or lower.startswith("falha na execução")
            or lower.startswith("❌")
        ):
            continue
        if compact in seen:
            continue
        seen.add(compact)
        cleaned.append(text)
    if normalized.get("has_error"):
        message = _clean(normalized.get("message"))
        technical = _clean(normalized.get("technical_detail"))
        if message:
            cleaned.append(f"❌ {message}")
        if technical:
            cleaned.append(f"[diagnóstico] {technical}")
    return cleaned[-250:]


def _script_block() -> str:
    try:
        source = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-update-flow-final>\n{source}\n</script>\n"


def _render_panel(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_update_flow_finalization_policy() -> None:
    global _INSTALLED, _BASE_JOB_PUBLIC, _BASE_HISTORY_ROWS, _BASE_COMBINED_LOGS
    global _BASE_RECOVERY_REUSE, _BASE_RECOVERY_MAKE, _BASE_SIMPLE_BATCH, _BASE_RENDER
    if _INSTALLED:
        return

    # Todas as preparações passam pelos mesmos adapters e pela mesma validação
    # concreta de sessão, independente de clique individual ou lote.
    web._build_update_preparation_service = _build_canonical_preparation_service

    # Recovery só pode repetir rede se o prepare ainda não tiver feito uma
    # tentativa final. Se a rede já respondeu HTML/erro, preservamos o erro e
    # aguardamos uma nova tentativa completa em vez de executar o mesmo request.
    _BASE_RECOVERY_REUSE = recoverability._reuse_or_download
    recoverability._reuse_or_download = _recovery_reuse_without_duplicate_network
    _BASE_RECOVERY_MAKE = recoverability._make_source_usable_again
    recoverability._make_source_usable_again = _recovery_make_with_diagnostic

    # Um executor para individual, lote simplificado e fila avançada.
    simple_flow._execute_update_one = execute_update_job
    _BASE_SIMPLE_BATCH = simple_flow._run_batch
    simple_flow._run_batch = _run_batch_canonical
    web._run_update_queue = _run_advanced_queue_canonical

    # Uma única origem normalizada alimenta card, histórico e API pública.
    _BASE_JOB_PUBLIC = runtime.job_public
    runtime.job_public = _public_job
    _BASE_HISTORY_ROWS = history_shared._update_rows
    history_shared._update_rows = _history_rows
    _BASE_COMBINED_LOGS = recoverability._combined_logs
    recoverability._combined_logs = _combined_logs

    # Ajustes finais de apresentação que não justificam reescrever panel.js.
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _render_panel
    _INSTALLED = True


__all__ = [
    "install_update_flow_finalization_policy",
    "execute_update_job",
    "_run_batch_canonical",
    "_run_advanced_queue_canonical",
]
