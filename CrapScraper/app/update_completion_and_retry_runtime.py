from __future__ import annotations

import json
from typing import Any

from app.comparison import decisions, matching
from app.updates.executor import UpdateExecutor
from app.updates.service import UpdateService


_INSTALLED = False
_ORIGINAL_EXECUTOR_EXECUTE = None
_ORIGINAL_EXECUTION = None
_ORIGINAL_LIST_APPROVED = None
_ORIGINAL_BUILD_FULL_COMPARISON = None

_DRIFT_MARKERS = (
    "versão da fonte divergiu da aprovação",
    "versao da fonte divergiu da aprovacao",
    "versão mudou desde a aprovação",
    "versao mudou desde a aprovacao",
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _version_key(value: Any) -> tuple[int, ...]:
    import re

    parts = tuple(int(part) for part in re.findall(r"\d+", _clean(value)))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts or (0,)


def _is_source_version_drift(error: Any) -> bool:
    payload = dict(error or {}) if isinstance(error, dict) else {}
    code = _clean(payload.get("code")).casefold()
    if code == "source_version_drift":
        return True
    text = " ".join(
        _clean(payload.get(key))
        for key in ("message", "technical_message", "diagnosis")
    ).casefold()
    return any(marker in text for marker in _DRIFT_MARKERS)


def _recoverable_job(job: dict[str, Any]) -> dict[str, Any]:
    if str(job.get("state") or "") != "error" or not _is_source_version_drift(job.get("error")):
        return job
    current = dict(job)
    error = dict(current.get("error") or {})
    error["recoverable"] = True
    error["code"] = "source_version_drift"
    current["error"] = error
    return current


def _persist_recoverable_drift(repository: Any, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok") or not _is_source_version_drift(result.get("error")):
        return result

    error = dict(result.get("error") or {})
    error["recoverable"] = True
    error["code"] = "source_version_drift"
    result = {**result, "error": error}
    attempt_id = _clean(result.get("attempt_id"))

    try:
        with repository.connection() as db:
            db.execute(
                "UPDATE update_jobs SET current_error=?, updated_at=datetime('now') WHERE job_id=?",
                (json.dumps(error, ensure_ascii=False), str(job_id)),
            )
            if attempt_id:
                db.execute(
                    "UPDATE update_attempts SET error=? WHERE attempt_id=?",
                    (json.dumps(error, ensure_ascii=False), attempt_id),
                )
    except Exception:
        # A correção do metadata de retry nunca transforma uma execução já
        # encerrada em uma nova falha. O resultado em memória continua correto.
        pass
    return result


def _list_approved_updates() -> list[dict[str, Any]]:
    """Somente aprovações ainda operacionais podem rematerializar jobs."""
    return decisions.list_decisions(decision="approve_update", queue_type="update")


def _mark_decision_updated(job: dict[str, Any]) -> bool:
    item_id = _clean(job.get("comparison_item_id"))
    if not item_id:
        return False

    decisions.initialize_database()
    now = decisions.utc_now_iso()
    target = _clean(job.get("source_version"))
    changed = False

    try:
        with decisions.database_connection() as db:
            row = db.execute(
                "SELECT * FROM comparison_decisions WHERE comparison_item_id=?",
                (item_id,),
            ).fetchone()
            if not row or str(row["decision"] or "") != "approve_update":
                return False
            if str(row["status"] or "") == "updated" and not str(row["queue_type"] or ""):
                return False

            previous = str(row["decision"] or "")
            note = _clean(row["note"])
            completion_note = f"Atualização concluída pelo CrapScraper para {target}." if target else "Atualização concluída pelo CrapScraper."
            history_note = f"{note} | {completion_note}".strip(" |").strip()

            db.execute(
                """
                UPDATE comparison_decisions
                SET decision_label='Atualizado', status='updated',
                    recommended_action='no_action', queue_type='',
                    site_version=CASE WHEN ?<>'' THEN ? ELSE site_version END,
                    operator='CrapScraper', updated_at=?
                WHERE comparison_item_id=?
                """,
                (target, target, now, item_id),
            )
            db.execute(
                """
                INSERT INTO comparison_decision_history(
                    comparison_item_id, previous_decision, new_decision,
                    note, operator, changed_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (item_id, previous, previous, history_note, "CrapScraper", now),
            )
            changed = True
    finally:
        if changed:
            # O snapshot da comparação é cacheado pelos arquivos CSV. A decisão
            # operacional mudou sem alterar esses arquivos, portanto o cache deve
            # ser invalidado explicitamente.
            matching._CACHE_KEY = None
            matching._CACHE_PAYLOAD = None
    return changed


def _completed_overlay_is_current(row: dict[str, Any], saved: dict[str, Any]) -> bool:
    if str(saved.get("status") or "") != "updated":
        return False
    completed_target = _clean(saved.get("source_version"))
    current_source = _clean(row.get("source_version"))
    if completed_target and current_source and _version_key(current_source) > _version_key(completed_target):
        # Uma versão mais nova surgiu na origem. Não esconda uma nova atualização
        # atrás do estado concluído anterior.
        return False
    return True


def _build_full_comparison(source_path: Any, site_path: Any) -> dict[str, Any]:
    payload = dict(_ORIGINAL_BUILD_FULL_COMPARISON(source_path, site_path))
    rows = [dict(row) for row in payload.get("rows", [])]
    ids = [str(row.get("comparison_item_id") or "") for row in rows]
    saved = decisions.get_decisions_map(ids)

    for row in rows:
        item_id = str(row.get("comparison_item_id") or "")
        decision = dict(saved.get(item_id) or {})
        if not _completed_overlay_is_current(row, decision):
            continue
        target = _clean(decision.get("source_version") or row.get("source_version"))
        row.update(
            status="updated",
            status_label="Atualizado",
            status_reason=(
                f"Atualização concluída pelo CrapScraper para a versão {target}; "
                "o próximo catálogo da PluginTema confirmará o snapshot."
                if target
                else "Atualização concluída pelo CrapScraper; o próximo catálogo da PluginTema confirmará o snapshot."
            ),
            recommended_action="no_action",
            recommended_action_label="Nenhuma ação necessária.",
            decision_label="Atualizado",
            decision_queue_type="",
        )
        if target:
            row["site_version"] = target
            row["version_comparison"] = 0

    payload["rows"] = rows
    labels = dict(payload.get("status_labels") or {})
    labels["updated"] = "Atualizado"
    payload["status_labels"] = labels
    counts = {key: 0 for key in labels}
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    payload["counts"] = counts
    return payload


def _execution(self: UpdateService, job: dict[str, Any]) -> dict[str, Any]:
    return _ORIGINAL_EXECUTION(self, _recoverable_job(job))


def _executor_execute(self: UpdateExecutor, job_id: str) -> dict[str, Any]:
    job = self.repository.get(job_id)
    result = dict(_ORIGINAL_EXECUTOR_EXECUTE(self, job_id))
    result = _persist_recoverable_drift(self.repository, job_id, result)
    if result.get("ok"):
        try:
            _mark_decision_updated({**job, "source_version": self.repository.get(job_id).get("source_version")})
        except Exception:
            # Uma atualização transacional já confirmada nunca deve virar erro
            # apenas porque a projeção administrativa da Comparação falhou.
            pass
    return result


def install_update_completion_and_retry_runtime() -> None:
    global _INSTALLED, _ORIGINAL_EXECUTOR_EXECUTE, _ORIGINAL_EXECUTION
    global _ORIGINAL_LIST_APPROVED, _ORIGINAL_BUILD_FULL_COMPARISON
    if _INSTALLED:
        return

    _ORIGINAL_EXECUTOR_EXECUTE = UpdateExecutor.execute
    _ORIGINAL_EXECUTION = UpdateService._execution
    _ORIGINAL_LIST_APPROVED = decisions.list_approved_updates
    _ORIGINAL_BUILD_FULL_COMPARISON = matching._build_full_comparison

    UpdateExecutor.execute = _executor_execute
    UpdateService._execution = _execution
    decisions.list_approved_updates = _list_approved_updates
    matching._build_full_comparison = _build_full_comparison
    _INSTALLED = True


__all__ = [
    "install_update_completion_and_retry_runtime",
    "_is_source_version_drift",
    "_recoverable_job",
    "_mark_decision_updated",
]
