from __future__ import annotations

import pytest

from app.integrations.ssh_helper import RestrictedSSHHelperClient, SSHHelperRequest
from app.integrations.wordpress import IntegrationError
from app.operations import runtime
from app.operations.models import JobState, OperationalJob
import app.update_queue_execution_reliability_policy as policy


def _queued_job() -> OperationalJob:
    job = OperationalJob(
        comparison_item_id="item-ekko",
        woo_product_id=95002,
        name="Ekko",
        plugintema_version="5.6",
        ultrapack_version="5.7",
        ultrapack_url="https://example.test/ekko",
        official_url="https://example.test/ekko",
        decision="approve_update",
        relationship="safe_auto",
        queue_type="update",
        approved_source_version="5.7",
        effective_source_version="5.7",
    )
    job.state = JobState.QUEUED
    job.queue_name = "default"
    job.queue_position = 1
    job.queued_at = "2026-08-18T21:00:00+00:00"
    return job


def test_claim_marks_job_executing_before_returning(monkeypatch) -> None:
    job = _queued_job()
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
            "status": "running",
            "active_queue": "default",
            "queues": {"default": {"created_at": "", "updated_at": ""}},
        })
        runtime._JOBS[job.job_id] = job
        runtime._PREVIEWS[job.job_id] = {"ready": True}
        runtime._PLANS[job.job_id] = {
            "ready": True,
            "job_id": job.job_id,
            "woo_product_id": job.woo_product_id,
        }

    try:
        claimed = policy._claim_next_queued_job()
        assert claimed is job
        assert runtime._JOBS[job.job_id] is job
        assert job.state == JobState.EXECUTING
        assert job.executing_at
        assert job.attempts == 1
    finally:
        with runtime._LOCK:
            runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
            runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(old_previews)
            runtime._PLANS.clear(); runtime._PLANS.update(old_plans)
            runtime._QUEUE_CONTROL.clear(); runtime._QUEUE_CONTROL.update(old_control)


def test_ineligible_queued_job_is_blocked_during_claim(monkeypatch) -> None:
    job = _queued_job()
    monkeypatch.setattr(runtime, "_persist", lambda: None)
    monkeypatch.setattr(runtime, "is_execution_eligible", lambda *_args, **_kwargs: False)

    with runtime._LOCK:
        old_jobs = dict(runtime._JOBS)
        old_control = dict(runtime._QUEUE_CONTROL)
        runtime._JOBS.clear()
        runtime._QUEUE_CONTROL.clear()
        runtime._QUEUE_CONTROL.update({
            "status": "running", "active_queue": "default", "queues": {"default": {}},
        })
        runtime._JOBS[job.job_id] = job
    try:
        assert policy._claim_next_queued_job() is None
        assert job.state == JobState.BLOCKED
        assert job.queue_position == 0
        assert "pré-condições" in job.execution_error.lower()
    finally:
        with runtime._LOCK:
            runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
            runtime._QUEUE_CONTROL.clear(); runtime._QUEUE_CONTROL.update(old_control)


class _NeverReadyChannel:
    def exit_status_ready(self) -> bool:
        return False

    def close(self) -> None:
        pass


class _Stream:
    def __init__(self) -> None:
        self.channel = _NeverReadyChannel()

    def read(self) -> bytes:
        return b""


class _SSH:
    def exec_command(self, _command: str, timeout: int = 0):
        return object(), _Stream(), _Stream()


def test_helper_has_real_deadline(monkeypatch) -> None:
    monkeypatch.setattr(policy, "_HELPER_TIMEOUT_SECONDS", 0.0)
    monkeypatch.setattr(policy.time, "sleep", lambda _seconds: None)
    helper = RestrictedSSHHelperClient(_SSH(), execution_enabled=True)
    request = SSHHelperRequest(
        "backup",
        "produto.zip",
        "job123",
        expected_sha256="a" * 64,
    )

    with pytest.raises(IntegrationError, match="excedeu 0s na operação backup"):
        policy._bounded_helper_invoke(helper, request)


def test_policy_is_installed_at_startup() -> None:
    from pathlib import Path

    main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "install_update_queue_execution_reliability_policy" in main
    assert "install_update_queue_execution_reliability_policy()" in main
