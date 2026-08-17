"""Recuperação conservadora de estados transitórios de preparação.

Estados como ``validating`` e ``downloading`` só podem existir enquanto há um
worker ativo. Se foram persistidos e o processo está iniciando novamente, a
preparação anterior foi interrompida. O job volta para ``approved`` sem apagar
o staging, SHA ou plano anterior; a próxima preparação fará todas as validações
novamente e poderá reaproveitar o ZIP local quando houver prova suficiente.
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
    recovered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for job in jobs:
        previous_state = _text(job.get("state")).lower()
        if previous_state not in _TRANSIENT_PREPARATION_STATES:
            continue

        job["state"] = "approved"
        job["queue_position"] = 0
        job["execution_error"] = (
            "A preparação anterior foi interrompida pelo encerramento ou reinício do CrapScraper. "
            "Prepare novamente; se houver ZIP local válido com SHA e versão compatíveis, ele será reaproveitado."
        )

        diagnostics = job.get("diagnostics")
        if not isinstance(diagnostics, list):
            diagnostics = []
            job["diagnostics"] = diagnostics
        diagnostics.append(
            f"Estado transitório {previous_state} recuperado para approved em {recovered_at}."
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
        })

        changes.append({
            "job_id": _text(job.get("job_id")),
            "woo_product_id": int(job.get("woo_product_id") or 0),
            "name": _text(job.get("name")),
            "previous_state": previous_state,
            "has_local_staging": bool(_text(job.get("local_staging_path"))),
            "has_sha256": bool(_text(job.get("new_sha256"))),
        })

    repaired["jobs"] = jobs
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
