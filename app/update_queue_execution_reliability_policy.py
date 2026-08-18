from __future__ import annotations

import json
import re
import time
from typing import Any, Mapping

import app.operations.runtime as runtime
import app.web as web
from app.integrations.ssh_helper import RestrictedSSHHelperClient, SSHHelperRequest
from app.integrations.wordpress import IntegrationError
from app.operations.models import JobState, utc_now_iso

_INSTALLED = False
_BASE_RUN_QUEUE = None
_BASE_HELPER_INVOKE = None
_HELPER_TIMEOUT_SECONDS = 180.0
_HELPER_POLL_SECONDS = 0.10


def _claim_next_queued_job() -> Any | None:
    """Reserva atomicamente o próximo job antes de o worker sair do lock.

    Sem esta reserva, o polling de ``/atualizacoes/jobs`` pode materializar a
    comparação entre ``next_queued_job`` e ``executor.execute`` e substituir o
    objeto que o worker está executando. O sintoma é exatamente um badge
    ``queued`` com logs de execução avançando em outro objeto destacado.
    """
    with runtime._LOCK:
        runtime._normalize_queue_control()
        if runtime._QUEUE_CONTROL.get("status") != "running":
            return None

        active_queue = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        candidates = sorted(
            (
                job
                for job in runtime._JOBS.values()
                if job.state == JobState.QUEUED
                and str(getattr(job, "queue_name", "default") or "default") == active_queue
            ),
            key=lambda job: (int(job.queue_position or 0), str(job.queued_at or "")),
        )

        changed = False
        for job in candidates:
            preview = runtime._PREVIEWS.get(job.job_id)
            plan = runtime._PLANS.get(job.job_id)
            if not runtime.is_execution_eligible(job, preview, plan):
                job.queue_position = 0
                job.execution_error = (
                    "Execução bloqueada: o job deixou de atender às pré-condições da fila."
                )
                job.set_state(
                    JobState.BLOCKED,
                    "Pré-condições de execução da fila não atendidas",
                )
                changed = True
                continue

            job.attempts += 1
            job.executing_at = utc_now_iso()
            job.execution_error = ""
            job.set_state(JobState.EXECUTING, "Execução da fila iniciada")
            # Persistir ainda dentro do mesmo lock é intencional: o materialize
            # passa a enxergar EXECUTING e preserva exatamente este objeto.
            runtime._persist()
            return job

        if changed:
            runtime._persist()
        return None


def _run_update_queue_reliable() -> None:
    """Worker sequencial que usa claim atômico em vez de obter um QUEUED solto."""
    while True:
        job = _claim_next_queued_job()
        if job is None:
            snapshot = runtime.queue_snapshot()
            if snapshot["status"] == "running" and not snapshot["queued"]:
                runtime.set_queue_status("stopped")
            return

        logger = web._UPDATE_LOGS.for_job(job.job_id)
        try:
            plan = runtime.get_plan(job.job_id)
            logger.clear()
            logger.log(f"Fila reservou Woo #{job.woo_product_id} para execução")
            executor = web._build_controlled_update_executor(job, logger.log)
            executor.execute(job, plan, f"EXECUTAR {job.woo_product_id}")
        except Exception as error:
            if job.state == JobState.EXECUTING:
                job.set_state(JobState.ERROR, "Falha técnica durante execução sequencial")
            job.execution_error = logger.sanitize(error)
            logger.log(f"Falha na execução: {job.execution_error}")
        finally:
            job.queue_position = 0
            job.execution_logs = logger.to_list()
            runtime.persist_job(job)


def _sanitize_helper_detail(value: Any) -> str:
    detail = str(value or "").strip()
    try:
        parsed = json.loads(detail)
        if isinstance(parsed, Mapping):
            detail = str(parsed.get("error") or parsed.get("message") or "").strip()
    except (TypeError, json.JSONDecodeError):
        pass
    return re.sub(
        r"(?i)(password|senha|consumer[_ -]?(?:key|secret)|authorization|cookie)\s*[:=]\s*[^\s,;]+",
        lambda match: match.group(1) + "=[redacted]",
        detail,
    )


def _bounded_helper_invoke(
    self: RestrictedSSHHelperClient,
    request: SSHHelperRequest,
) -> Mapping[str, Any]:
    """Executa o helper com deadline real inclusive durante recv_exit_status()."""
    if not self.execution_enabled:
        from app.integrations.wordpress import WriteOperationDisabledError

        raise WriteOperationDisabledError("Execucao remota do helper desabilitada nesta fase")
    if self._ssh_client is None:
        raise IntegrationError("Conexao SSH nao configurada")

    command = self.command(request)
    try:
        _stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=30)
    except Exception as error:
        raise IntegrationError(
            f"Falha ao iniciar helper remoto ({request.operation}): {_sanitize_helper_detail(error)}"
        ) from None

    channel = stdout.channel
    deadline = time.monotonic() + _HELPER_TIMEOUT_SECONDS
    while not channel.exit_status_ready():
        if time.monotonic() >= deadline:
            try:
                channel.close()
            except Exception:
                pass
            raise IntegrationError(
                f"Helper remoto excedeu {int(_HELPER_TIMEOUT_SECONDS)}s na operação {request.operation}"
            )
        time.sleep(_HELPER_POLL_SECONDS)

    status = channel.recv_exit_status()
    raw = stdout.read().decode("utf-8", "replace")
    raw_error = stderr.read().decode("utf-8", "replace")
    if status != 0:
        detail = _sanitize_helper_detail(raw_error or raw)
        raise IntegrationError(
            f"Helper remoto retornou falha: {detail}" if detail else "Helper remoto retornou falha"
        )

    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise IntegrationError("Resposta JSON invalida do helper") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise IntegrationError("Helper remoto nao confirmou sucesso")
    return result


def install_update_queue_execution_reliability_policy() -> None:
    global _INSTALLED, _BASE_RUN_QUEUE, _BASE_HELPER_INVOKE
    if _INSTALLED:
        return

    _BASE_RUN_QUEUE = web._run_update_queue
    web._run_update_queue = _run_update_queue_reliable

    _BASE_HELPER_INVOKE = RestrictedSSHHelperClient.invoke
    RestrictedSSHHelperClient.invoke = _bounded_helper_invoke

    _INSTALLED = True
