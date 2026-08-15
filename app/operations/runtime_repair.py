"""Repara estados persistidos que não possuem evidência suficiente de conclusão real.

A regra é conservadora: um job só pode permanecer como ``completed`` quando o
runtime contém evidências compatíveis com uma execução real já confirmada.
Estados legados ou incompletos são movidos para ``blocked`` para exigir nova
preparação/revalidação em vez de aparecerem como concluídos sem prova.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from app import settings


_COMPLETED = "completed"
_BLOCKED = "blocked"
_REQUIRED_LAST_STEP = "pt_versao_updated"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def completion_evidence(job: Mapping[str, Any], plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retorna diagnóstico objetivo das provas persistidas de uma conclusão."""
    raw_job = dict(job or {})
    raw_plan = dict(plan or {})
    evidence = _mapping(raw_job.get("version_write_evidence"))
    new_zip = _mapping(raw_plan.get("new_zip"))

    effective_version = _text(
        raw_job.get("effective_source_version")
        or raw_job.get("ultrapack_version")
    )
    confirmed_version = _text(evidence.get("get_pt_versao"))
    planned_sha = _text(new_zip.get("sha256"))
    persisted_sha = _text(raw_job.get("new_sha256"))

    checks = {
        "completed_at": bool(_text(raw_job.get("completed_at"))),
        "last_step": _text(raw_job.get("last_completed_step")) == _REQUIRED_LAST_STEP,
        "plan_ready": raw_plan.get("ready") is True,
        "plan_job": _text(raw_plan.get("job_id")) == _text(raw_job.get("job_id")),
        "plan_product": int(raw_plan.get("woo_product_id") or 0)
        == int(raw_job.get("woo_product_id") or 0),
        "effective_version": bool(effective_version),
        "version_confirmed": bool(confirmed_version)
        and confirmed_version == effective_version,
        "planned_sha": bool(planned_sha),
        "persisted_sha": bool(persisted_sha) and persisted_sha == planned_sha,
    }

    return {
        "ok": all(checks.values()),
        "checks": checks,
        "effective_version": effective_version,
        "confirmed_version": confirmed_version,
        "planned_sha256": planned_sha,
        "persisted_sha256": persisted_sha,
    }


def repair_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rebaixa conclusões sem evidência; não toca em preparados, fila ou erros."""
    repaired = dict(payload or {})
    jobs = [dict(item) for item in repaired.get("jobs", []) if isinstance(item, Mapping)]
    plans = _mapping(repaired.get("plans"))
    changes: list[dict[str, Any]] = []

    for job in jobs:
        if _text(job.get("state")).lower() != _COMPLETED:
            continue

        job_id = _text(job.get("job_id"))
        diagnostic = completion_evidence(job, _mapping(plans.get(job_id)))
        if diagnostic["ok"]:
            continue

        previous_completed_at = _text(job.get("completed_at"))
        previous_last_step = _text(job.get("last_completed_step"))
        failed_checks = [key for key, ok in diagnostic["checks"].items() if not ok]

        history = job.get("execution_history")
        if not isinstance(history, list):
            history = []
            job["execution_history"] = history
        history.append(
            {
                "result": "completion_quarantined",
                "reason": "Conclusão persistida sem evidência suficiente de atualização real",
                "failed_checks": failed_checks,
                "completed_at": previous_completed_at,
                "last_completed_step": previous_last_step,
            }
        )

        job["state"] = _BLOCKED
        job["completed_at"] = ""
        job["queue_position"] = 0
        job["execution_error"] = (
            "Conclusão anterior colocada em quarentena: faltam evidências de que "
            "ZIP de produção e pt_versao foram realmente confirmados. Prepare e "
            "execute novamente após revisar os pré-requisitos."
        )
        diagnostics = job.get("diagnostics")
        if not isinstance(diagnostics, list):
            diagnostics = []
            job["diagnostics"] = diagnostics
        diagnostics.append(
            "Estado completed legado/incompleto rebaixado automaticamente para blocked."
        )

        changes.append(
            {
                "job_id": job_id,
                "woo_product_id": int(job.get("woo_product_id") or 0),
                "name": _text(job.get("name")),
                "failed_checks": failed_checks,
            }
        )

    repaired["jobs"] = jobs
    return repaired, changes


def repair_update_runtime(path: str | Path | None = None) -> dict[str, Any]:
    """Executa reparo atômico do update_runtime.json e devolve um resumo seguro."""
    runtime_path = Path(path or settings.UPDATE_RUNTIME_PATH)
    if not runtime_path.exists():
        return {"changed": 0, "jobs": [], "path": str(runtime_path)}

    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"changed": 0, "jobs": [], "path": str(runtime_path), "invalid": True}

    repaired, changes = repair_payload(payload)
    if changes:
        temporary = runtime_path.with_suffix(runtime_path.suffix + ".repair.tmp")
        temporary.write_text(
            json.dumps(repaired, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(runtime_path)

    return {"changed": len(changes), "jobs": changes, "path": str(runtime_path)}
