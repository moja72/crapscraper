from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.integrations.woocommerce import pt_versao
from app.operations.models import JobState, OperationalJob, record_execution_outcome
from app.operations.real_executor import ControlledUpdateExecutor

_INSTALLED = False
_BASE_EXECUTE = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    return str(value or "").strip().lstrip("vV")


def _patched_execute(
    self: ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    # Mantém as mesmas regras de autorização do executor real antes de qualquer leitura/decisão.
    self.authorize(job, plan, confirmation)

    expected = _norm(plan.get("effective_source_version") or job.effective_source_version)
    product_reader = getattr(self.woo, "get_product_fresh", self.woo.get_product)
    product = product_reader(job.woo_product_id)
    current = _norm(pt_versao(product))

    if expected and current and current == expected:
        message = f"Destino já está na versão {expected}; nenhuma alteração foi necessária."
        job.execution_error = ""
        job.completed_at = _now()
        job.last_completed_step = "already_current"
        job.set_state(JobState.COMPLETED, message)
        record_execution_outcome(job, dict(plan), "already_current")
        self.log(f"ℹ {message}")
        self.log("ℹ ZIP e pt_versao não foram alterados porque o produto já estava atualizado.")
        return {
            "ok": True,
            "state": job.state.value,
            "already_current": True,
            "completed_at": job.completed_at,
            "message": message,
        }

    return _BASE_EXECUTE(self, job, plan, confirmation)


def install_already_current_update_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE
    if _INSTALLED:
        return
    _BASE_EXECUTE = ControlledUpdateExecutor.execute
    ControlledUpdateExecutor.execute = _patched_execute
    _INSTALLED = True
