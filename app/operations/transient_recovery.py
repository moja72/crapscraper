"""Recuperação conservadora de estados transitórios de preparação.

Estados como ``validating`` e ``downloading`` só podem existir enquanto há um
worker ativo. Se foram persistidos e o processo está iniciando novamente, a
preparação anterior foi interrompida. O job volta para ``approved`` sem apagar
staging/SHA. Preview e plano incompletos são descartados para que a próxima
preparação revalide tudo antes de reaproveitar qualquer ZIP local.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app import settings

_TRANSIENT_PREPARATION_STATES = {"validating", "downloading", "staging", "preparing"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def recover_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repaired = dict(payload or {})
    jobs = [dict(item) for item in repaired.get("jobs", []) if isinstance(item, Mapping)]
    changes: list[dict[str, Any]] = []
    recovered_ids: set[str] = set()
    recovered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for job in jobs:
        previous_state = _text(job.get("state")).lower()
        if previous_state not in _TRANSIENT_PREPARATION_STATES:
            continue

        job_id = _text(job.get("job_id"))
        if job_id:
            recovered_ids.add(job_id)

        job["state"] = "approved"
        job["queue_position"] = 0
        job["execution_error"] = ""

        diagnostics = job.get("diagnostics")
        if not isinstance(diagnostics, list):
            diagnostics = []
            job["diagnostics"] = diagnostics
        diagnostics.append(
            f"Preparação interrompida em {previous_state} recuperada para approved em {recovered_at}; "
            "preview/plano incompletos foram descartados e o staging local foi preservado."
        )

        history = job.get("execution_history")
        if not isinstance(history, list):
            history = []
            job["execution_history"] = history
        history.append({
            "result": "preparation_interrupted",
            "previous_state": previous_state,
            "recovered_state": "approved",
            "recovered_at": recovered_at,
            "local_staging_preserved": bool(_text(job.get("local_staging_path"))),
            "new_sha256_preserved": bool(_text(job.get("new_sha256"))),
            "stale_preview_removed": True,
            "stale_plan_removed": True,
        })

        changes.append({
            "job_id": job_id,
            "woo_product_id": int(job.get("woo_product_id") or 0),
            "name": _text(job.get("name")),
            "previous_state": previous_state,
            "has_local_staging": bool(_text(job.get("local_staging_path"))),
            "has_sha256": bool(_text(job.get("new_sha256"))),
        })

    repaired["jobs"] = jobs

    # Preview/plano gerados antes de um encerramento podem apontar para estado,
    # versão ou staging que não chegaram ao fim. Removê-los evita um falso
    # bloqueio no próximo clique em "Preparar e gerar plano". O ZIP local e seu
    # SHA continuam no próprio job e só serão reutilizados após nova validação.
    for key in ("previews", "plans"):
        current = repaired.get(key)
        if not isinstance(current, Mapping):
            continue
        repaired[key] = {
            str(job_id): value
            for job_id, value in current.items()
            if str(job_id) not in recovered_ids
        }

    return repaired, changes


def recover_interrupted_preparations(path: str | Path | None = None) -> dict[str, Any]:
    runtime_path = Path(path or settings.UPDATE_RUNTIME_PATH)
    if not runtime_path.exists():
        return {"changed": 0, "jobs": [], "path": str(runtime_path)}

    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"changed": 0, "jobs": [], "path": str(runtime_path), "invalid": True}

    repaired, changes = recover_payload(payload)
    if changes:
        temporary = runtime_path.with_suffix(runtime_path.suffix + ".transient.tmp")
        temporary.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(runtime_path)

    return {"changed": len(changes), "jobs": changes, "path": str(runtime_path)}
