from __future__ import annotations

from app.operations import runtime
from app.operations.models import JobState, OperationalJob
from app.operations.runtime_repair import repair_payload
from app.update_queue_lifecycle_policy import _enqueue_plan_ready_job


def test_quarantined_completed_job_is_restored_from_success_history() -> None:
    job_id = "job-affirm"
    sha = "a" * 64
    payload = {
        "jobs": [{
            "job_id": job_id,
            "woo_product_id": 95317,
            "name": "Affirm",
            "state": "blocked",
            "plugintema_version": "4.3.3",
            "ultrapack_version": "4.4.1",
            "effective_source_version": "4.4.1",
            "completed_at": "",
            "executing_at": "2026-08-18T19:32:54+00:00",
            "last_completed_step": "pt_versao_updated",
            "new_sha256": sha,
            "execution_error": (
                "Conclusão anterior colocada em quarentena: faltam evidências de que "
                "ZIP de produção e pt_versao foram realmente confirmados."
            ),
            "execution_history": [
                {
                    "result": "completed",
                    "executing_at": "2026-08-18T19:32:54+00:00",
                    "completed_at": "2026-08-18T19:33:11+00:00",
                    "last_completed_step": "pt_versao_updated",
                    "new_sha256": sha,
                    "plan_id": "plan-1",
                },
                {
                    "result": "completion_quarantined",
                    "completed_at": "2026-08-18T19:33:11+00:00",
                    "last_completed_step": "pt_versao_updated",
                },
            ],
            "diagnostics": [],
        }],
        "plans": {
            job_id: {
                "plan_id": "plan-1",
                "job_id": job_id,
                "woo_product_id": 95317,
                "ready": True,
                "new_zip": {"sha256": sha},
            }
        },
    }

    repaired, changes = repair_payload(payload)

    job = repaired["jobs"][0]
    assert job["state"] == "completed"
    assert job["completed_at"] == "2026-08-18T19:33:11+00:00"
    assert job["execution_error"] == ""
    assert changes[0]["action"] == "restored"
    assert changes[0]["evidence"] == "execution_history"


def test_unproven_completed_job_is_still_quarantined() -> None:
    payload = {
        "jobs": [{
            "job_id": "job-unproven",
            "woo_product_id": 10,
            "name": "Sem prova",
            "state": "completed",
            "effective_source_version": "2.0",
            "completed_at": "2026-08-18T19:00:00+00:00",
            "last_completed_step": "pt_versao_updated",
            "new_sha256": "",
            "execution_history": [],
            "diagnostics": [],
        }],
        "plans": {},
    }

    repaired, changes = repair_payload(payload)

    assert repaired["jobs"][0]["state"] == "blocked"
    assert changes[0]["action"] == "quarantined"


def _ready_job() -> OperationalJob:
    job = OperationalJob(
        comparison_item_id="item-egovt",
        woo_product_id=95878,
        name="EGovt",
        plugintema_version="1.6.6",
        ultrapack_version="1.6.7",
        ultrapack_url="https://example.test/egovt",
        official_url="https://example.test/egovt",
        decision="approve_update",
        relationship="safe_auto",
        queue_type="update",
        approved_source_version="1.6.7",
        effective_source_version="1.6.7",
    )
    job.state = JobState.PLAN_READY
    job.queue_name = "default"
    return job


def test_plan_ready_job_is_really_enqueued(monkeypatch) -> None:
    job = _ready_job()
    monkeypatch.setattr(runtime, "_persist", lambda: None)
    monkeypatch.setattr(runtime, "is_execution_eligible", lambda *_args, **_kwargs: True)

    with runtime._LOCK:
        old_jobs = dict(runtime._JOBS)
        old_previews = dict(runtime._PREVIEWS)
        old_plans = dict(runtime._PLANS)
        old_control = dict(runtime._QUEUE_CONTROL)
        runtime._JOBS.clear()
        runtime._PREVIEWS.clear()
        runtime._PLANS.clear()
        runtime._QUEUE_CONTROL.clear()
        runtime._QUEUE_CONTROL.update({
            "status": "stopped",
            "active_queue": "default",
            "queues": {"default": {"created_at": "", "updated_at": ""}},
        })
        runtime._JOBS[job.job_id] = job
        runtime._PREVIEWS[job.job_id] = {"ready": True}
        runtime._PLANS[job.job_id] = {"ready": True, "job_id": job.job_id, "woo_product_id": job.woo_product_id}

    try:
        added = _enqueue_plan_ready_job(job.job_id)
        assert len(added) == 1
        assert runtime._JOBS[job.job_id].state == JobState.QUEUED
        assert runtime._JOBS[job.job_id].queue_position == 1
        assert runtime._JOBS[job.job_id].queue_name == "default"
    finally:
        with runtime._LOCK:
            runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
            runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(old_previews)
            runtime._PLANS.clear(); runtime._PLANS.update(old_plans)
            runtime._QUEUE_CONTROL.clear(); runtime._QUEUE_CONTROL.update(old_control)
