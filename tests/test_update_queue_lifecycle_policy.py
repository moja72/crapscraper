from __future__ import annotations

from app.operations.models import JobState, OperationalJob
import app.operations.runtime as runtime
import app.update_queue_lifecycle_policy as policy


def test_attach_plan_ready_job_uses_active_queue(tmp_path, monkeypatch):
    job = OperationalJob(
        comparison_item_id="item-1",
        woo_product_id=123,
        name="Produto",
        plugintema_version="1.0",
        ultrapack_version="1.1",
        ultrapack_url="https://example.invalid/produto",
        official_url="https://example.invalid",
        decision="approve_update",
        relationship="safe_auto",
        queue_type="update",
        approved_source_version="1.1",
        effective_source_version="1.1",
    )
    job.set_state(JobState.PLAN_READY, "Plano pronto")

    monkeypatch.setattr(runtime, "_JOBS", {job.job_id: job})
    monkeypatch.setattr(runtime, "_PREVIEWS", {})
    monkeypatch.setattr(runtime, "_PLANS", {})
    monkeypatch.setattr(runtime, "_DISMISSED_HISTORY", {})
    monkeypatch.setattr(runtime, "_QUEUE_CONTROL", {
        "status": "stopped",
        "updated_at": "",
        "active_queue": "Teste",
        "queues": {"default": {}, "Teste": {}},
    })
    monkeypatch.setattr(runtime, "_persist", lambda: None)

    policy._attach_plan_ready_job_to_active_queue(job.job_id)

    assert job.queue_name == "Teste"
    assert job.state == JobState.PLAN_READY
