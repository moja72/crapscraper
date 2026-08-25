from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from app import settings
import app.operational_simple_flow_policy as simple_flow
import app.operations.runtime as runtime
from app.operations.models import JobState


_INSTALLED = False
_BASE_EXECUTE_UPDATE_ONE: Callable[..., Any] | None = None
_GENERIC_EXECUTION_ERROR = (
    "o produto foi preparado, mas a execução real não está habilitada "
    "ou alguma pré-condição deixou de ser válida"
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _retryable(job: Any, plan: Mapping[str, Any]) -> bool:
    planned_backup = _text((plan.get("backup") or {}).get("path"))
    return bool(
        getattr(job, "state", None) == JobState.ERROR
        and _text(getattr(job, "last_completed_step", ""))
        in {"backup_validated", "staging_upload_validated"}
        and planned_backup
        and _text(getattr(job, "backup_path", "")) == planned_backup
    )


def execution_ineligibility_reasons(
    job: Any,
    preview: Mapping[str, Any] | None,
    plan: Mapping[str, Any] | None,
) -> list[str]:
    """Explica exatamente qual predicado do gate de execução não foi atendido."""
    candidate_preview = dict(preview or {})
    candidate_plan = dict(plan or {})
    reasons: list[str] = []

    if not settings.UPDATE_EXECUTION_ENABLED:
        reasons.append("SCRAPER_UPDATE_EXECUTION_ENABLED não está habilitado")

    state = getattr(job, "state", None)
    if state not in {JobState.PLAN_READY, JobState.QUEUED} and not _retryable(job, candidate_plan):
        label = getattr(state, "value", state) or "desconhecido"
        reasons.append(f"estado do job é {label}, mas deveria ser plan_ready/queued")

    if candidate_preview.get("ready") is not True:
        reasons.append("preview preparado não está ready=true")
    if candidate_plan.get("ready") is not True:
        reasons.append("plano de execução não está ready=true")

    job_id = _text(getattr(job, "job_id", ""))
    if _text(candidate_plan.get("job_id")) != job_id:
        reasons.append("plano pertence a outro job ou não possui job_id")

    woo_product_id = int(getattr(job, "woo_product_id", 0) or 0)
    try:
        planned_product_id = int(candidate_plan.get("woo_product_id") or 0)
    except (TypeError, ValueError):
        planned_product_id = 0
    if planned_product_id != woo_product_id:
        reasons.append("WooCommerce ID do plano diverge do job")

    relationship = _text(getattr(job, "relationship", ""))
    if relationship not in runtime.SAFE_EXECUTION_RELATIONSHIPS:
        reasons.append(f"vínculo {relationship or '-'} não é seguro para execução")

    allowed = settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS
    if allowed and woo_product_id not in allowed:
        ids = ", ".join(str(item) for item in sorted(allowed))
        reasons.append(
            "WooCommerce ID não está na allowlist de homologação "
            f"SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS ({ids})"
        )

    local_path = _text((candidate_plan.get("new_zip") or {}).get("local_staging_path"))
    if not local_path:
        reasons.append("plano não possui caminho local do novo ZIP")
    elif not Path(local_path).is_file():
        reasons.append(f"novo ZIP local não existe mais: {local_path}")

    return reasons


def _patched_execute_update_one(job_id: str, manager: Any) -> dict[str, Any]:
    if _BASE_EXECUTE_UPDATE_ONE is None:
        raise RuntimeError("Executor simplificado base indisponível")
    try:
        return _BASE_EXECUTE_UPDATE_ONE(job_id, manager)
    except RuntimeError as error:
        message = _text(error)
        if _GENERIC_EXECUTION_ERROR not in message.lower():
            raise

        try:
            job = runtime.get_job(job_id)
        except Exception:
            raise
        try:
            preview = runtime.get_preview(job_id)
        except Exception:
            preview = None
        try:
            plan = runtime.get_plan(job_id)
        except Exception:
            plan = None

        reasons = execution_ineligibility_reasons(job, preview, plan)
        if not reasons:
            raise
        raise RuntimeError("Execução bloqueada: " + "; ".join(reasons) + ".") from None


def install_operational_simple_flow_execution_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE_UPDATE_ONE
    if _INSTALLED:
        return
    _BASE_EXECUTE_UPDATE_ONE = simple_flow._execute_update_one
    simple_flow._execute_update_one = _patched_execute_update_one
    _INSTALLED = True
