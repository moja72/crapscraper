from __future__ import annotations

from app.operations import runtime
from app.operations.models import JobState, OperationalJob
from app.process_observability_policy import _repair_successful_terminal_state


def _job() -> OperationalJob:
    return OperationalJob(
        comparison_item_id="item-1",
        woo_product_id=95317,
        name="Affirm",
        plugintema_version="4.3.3",
        ultrapack_version="4.4.1",
        ultrapack_url="https://example.test/affirm",
        official_url="https://example.test/affirm",
        decision="approve_update",
        relationship="safe_auto",
        queue_type="update",
        approved_source_version="4.4.1",
        effective_source_version="4.4.1",
    )


def test_success_evidence_repairs_contradictory_blocked_state(monkeypatch) -> None:
    job = _job()
    job.state = JobState.BLOCKED
    job.executing_at = "2026-08-18T19:32:54+00:00"
    job.completed_at = "2026-08-18T19:33:11+00:00"
    job.last_completed_step = "pt_versao_updated"
    job.execution_error = ""
    job.execution_history = [{
        "result": "completed",
        "executing_at": job.executing_at,
        "completed_at": job.completed_at,
        "plan_id": "plan-1",
    }]

    monkeypatch.setattr(runtime, "_persist", lambda: None)
    with runtime._LOCK:
        runtime._JOBS[job.job_id] = job
    try:
        repaired = _repair_successful_terminal_state(runtime.job_public(job))
        assert repaired["state"] == "completed"
        assert runtime._JOBS[job.job_id].state == JobState.COMPLETED
        assert runtime._JOBS[job.job_id].execution_error == ""
    finally:
        with runtime._LOCK:
            runtime._JOBS.pop(job.job_id, None)


def test_logs_or_last_step_without_persisted_success_do_not_promote_job(monkeypatch) -> None:
    job = _job()
    job.state = JobState.BLOCKED
    job.executing_at = "2026-08-18T19:32:54+00:00"
    job.completed_at = "2026-08-18T19:33:11+00:00"
    job.last_completed_step = "pt_versao_updated"
    job.execution_logs = ["pt_versao confirmado: 4.4.1", "Atualização concluída"]
    job.execution_history = []

    monkeypatch.setattr(runtime, "_persist", lambda: None)
    with runtime._LOCK:
        runtime._JOBS[job.job_id] = job
    try:
        unchanged = _repair_successful_terminal_state(runtime.job_public(job))
        assert unchanged["state"] == "blocked"
        assert runtime._JOBS[job.job_id].state == JobState.BLOCKED
    finally:
        with runtime._LOCK:
            runtime._JOBS.pop(job.job_id, None)


def test_state_sync_script_updates_badge_and_stale_homologation_copy() -> None:
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "app" / "static" / "update_state_sync.js"
    ).read_text(encoding="utf-8")
    assert 'completed: "Concluído"' in script
    assert 'reason.remove()' in script
    assert "Execução concluída com sucesso" in script
    assert "Execução concluída e registrada no histórico" in script


def test_individual_update_owns_prepare_plan_execute_without_touching_batch_button() -> None:
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "app" / "static" / "update_state_sync.js"
    ).read_text(encoding="utf-8")

    assert 'button.textContent = "Preparando…"' in script
    assert 'postJson("/atualizacoes/preparar"' in script
    assert 'button.textContent = "Gerando plano…"' in script
    assert 'postJson("/atualizacoes/plano"' in script
    assert 'button.textContent = "Executando…"' in script
    assert 'postJson("/atualizacoes/executar"' in script
    assert 'button.dataset.csIndividualBusy' in script
    assert 'label === "executar" || label === "tentar novamente"' in script
    assert '#updates_queue_start' not in script


def test_retryable_individual_states_reenter_same_prepare_plan_path() -> None:
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "app" / "static" / "update_state_sync.js"
    ).read_text(encoding="utf-8")

    assert 'const RETRYABLE_STATES = new Set(["blocked", "error", "failed", "interrupted", "canceled"]);' in script
    assert 'RETRYABLE_STATES.has(text(job.state))' in script
    assert 'text(job.state) === "rollback_required"' in script
