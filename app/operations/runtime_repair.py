"""Repara estados persistidos do runtime de atualizações.

A política continua conservadora, mas reconhece como prova forte o registro de
execução ``completed`` criado pelo executor somente depois da validação final do
ZIP de produção e do ``pt_versao``. Isso também permite recuperar jobs que uma
versão anterior deste reparador colocou em quarentena indevidamente.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from app import settings


_COMPLETED = "completed"
_BLOCKED = "blocked"
_REQUIRED_LAST_STEP = "pt_versao_updated"
_SUCCESS_RESULTS = frozenset({"completed", "already_current"})
_SUCCESS_LAST_STEPS = frozenset({_REQUIRED_LAST_STEP, "already_current"})
_QUARANTINE_ERROR_PREFIX = "Conclusão anterior colocada em quarentena:"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _success_history(job: Mapping[str, Any]) -> dict[str, Any]:
    history = job.get("execution_history")
    if not isinstance(history, list):
        return {}
    for raw in reversed(history):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        if _text(item.get("result")) in _SUCCESS_RESULTS:
            return item
    return {}


def _was_quarantined(job: Mapping[str, Any]) -> bool:
    if _text(job.get("state")).lower() != _BLOCKED:
        return False
    if _text(job.get("execution_error")).startswith(_QUARANTINE_ERROR_PREFIX):
        return True
    history = job.get("execution_history")
    return isinstance(history, list) and any(
        isinstance(item, Mapping) and _text(item.get("result")) == "completion_quarantined"
        for item in history
    )


def completion_evidence(job: Mapping[str, Any], plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retorna diagnóstico objetivo das provas persistidas de uma conclusão.

    Há duas rotas válidas de evidência:
    1. confirmação detalhada do writer de ``pt_versao``; ou
    2. ``execution_history`` com resultado de sucesso do ciclo, registrado somente
       após a validação final feita pelo executor real.
    """
    raw_job = dict(job or {})
    raw_plan = dict(plan or {})
    evidence = _mapping(raw_job.get("version_write_evidence"))
    new_zip = _mapping(raw_plan.get("new_zip"))
    success = _success_history(raw_job)

    effective_version = _text(
        raw_job.get("effective_source_version")
        or raw_job.get("ultrapack_version")
    )
    confirmed_version = _text(evidence.get("get_pt_versao"))
    planned_sha = _text(new_zip.get("sha256"))
    persisted_sha = _text(raw_job.get("new_sha256"))
    history_sha = _text(success.get("new_sha256"))
    success_result = _text(success.get("result"))

    completed_at = _text(raw_job.get("completed_at") or success.get("completed_at"))
    executing_at = _text(raw_job.get("executing_at") or success.get("executing_at"))
    last_step = _text(raw_job.get("last_completed_step") or success.get("last_completed_step"))

    plan_checks = {
        "plan_ready": raw_plan.get("ready") is True,
        "plan_job": _text(raw_plan.get("job_id")) == _text(raw_job.get("job_id")),
        "plan_product": int(raw_plan.get("woo_product_id") or 0)
        == int(raw_job.get("woo_product_id") or 0),
        "effective_version": bool(effective_version),
    }

    writer_checks = {
        "completed_at": bool(completed_at),
        "last_step": last_step == _REQUIRED_LAST_STEP,
        **plan_checks,
        "version_confirmed": bool(confirmed_version)
        and confirmed_version == effective_version,
        "planned_sha": bool(planned_sha),
        "persisted_sha": bool(persisted_sha) and persisted_sha == planned_sha,
    }

    history_identity_ok = bool(success) and bool(completed_at) and bool(executing_at or success.get("completed_at"))
    history_common_ok = all(plan_checks.values()) and history_identity_ok and last_step in _SUCCESS_LAST_STEPS

    if success_result == "already_current":
        # Este resultado é gravado quando o destino já possui a versão efetiva;
        # nenhuma troca de ZIP é feita por definição.
        history_ok = history_common_ok and last_step == "already_current"
    else:
        # Para uma execução real normal, o histórico precisa apontar para o mesmo
        # SHA planejado que foi validado antes de ``record_execution_outcome``.
        sha_matches = bool(planned_sha) and (
            (bool(history_sha) and history_sha == planned_sha)
            or (bool(persisted_sha) and persisted_sha == planned_sha)
        )
        history_ok = (
            history_common_ok
            and success_result == "completed"
            and last_step == _REQUIRED_LAST_STEP
            and sha_matches
        )

    writer_ok = all(writer_checks.values())
    checks = {
        **writer_checks,
        "success_history": bool(success),
        "history_result": success_result in _SUCCESS_RESULTS,
        "history_sha": bool(history_sha),
    }

    return {
        "ok": writer_ok or history_ok,
        "writer_ok": writer_ok,
        "history_ok": history_ok,
        "checks": checks,
        "effective_version": effective_version,
        "confirmed_version": confirmed_version,
        "planned_sha256": planned_sha,
        "persisted_sha256": persisted_sha,
        "history_sha256": history_sha,
        "success_result": success_result,
        "success_completed_at": _text(success.get("completed_at")),
        "success_executing_at": _text(success.get("executing_at")),
    }


def _restore_quarantined_completion(
    job: dict[str, Any], diagnostic: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Restaura somente quarentenas que agora possuem prova persistida suficiente."""
    if not _was_quarantined(job) or not bool(diagnostic.get("ok")):
        return None

    success = _success_history(job)
    completed_at = _text(job.get("completed_at") or success.get("completed_at"))
    if not completed_at:
        return None

    job["state"] = _COMPLETED
    job["completed_at"] = completed_at
    if not _text(job.get("executing_at")):
        job["executing_at"] = _text(success.get("executing_at"))
    if not _text(job.get("last_completed_step")):
        job["last_completed_step"] = _text(success.get("last_completed_step")) or _REQUIRED_LAST_STEP
    job["queue_position"] = 0
    job["execution_error"] = ""

    diagnostics = job.get("diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
        job["diagnostics"] = diagnostics
    marker = "Conclusão restaurada a partir das evidências persistidas da execução real."
    if not diagnostics or diagnostics[-1] != marker:
        diagnostics.append(marker)

    return {
        "action": "restored",
        "job_id": _text(job.get("job_id")),
        "woo_product_id": int(job.get("woo_product_id") or 0),
        "name": _text(job.get("name")),
        "evidence": "execution_history" if diagnostic.get("history_ok") else "version_writer",
    }


def repair_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repara conclusões e recupera quarentenas comprovadamente válidas."""
    repaired = dict(payload or {})
    jobs = [dict(item) for item in repaired.get("jobs", []) if isinstance(item, Mapping)]
    plans = _mapping(repaired.get("plans"))
    changes: list[dict[str, Any]] = []

    for job in jobs:
        job_id = _text(job.get("job_id"))
        diagnostic = completion_evidence(job, _mapping(plans.get(job_id)))

        restored = _restore_quarantined_completion(job, diagnostic)
        if restored is not None:
            changes.append(restored)
            continue

        if _text(job.get("state")).lower() != _COMPLETED:
            continue
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
                "action": "quarantined",
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
