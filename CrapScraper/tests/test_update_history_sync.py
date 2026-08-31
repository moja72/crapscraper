from __future__ import annotations

from app.updates.history import UpdateHistorySynchronizer
from app.updates.repository import UpdateRepository
from tests.update_fakes import approval


class HistoryClient:
    configured = True

    def __init__(self, *, persisted=True, fail=False, wrong_timestamp=False):
        self.persisted, self.fail, self.wrong_timestamp = persisted, fail, wrong_timestamp
        self.sent = []

    def send_history(self, event):
        if self.fail:
            raise ConnectionError("offline")
        self.sent.append(dict(event))
        return {"ok": True}

    def confirm_history(self, operation_id):
        event = dict(self.sent[-1])
        if not self.persisted:
            event["new_version"] = "9.9.9"
        if self.wrong_timestamp:
            event["completed_at"] = "2026-08-30 03:42:00"
        return {"ok": True, "event": event}


def event(repository: UpdateRepository, *, success=True, stage="completed"):
    repository.materialize([approval()])
    job = repository.list()["items"][0]
    attempt = repository.begin_attempt(job["job_id"])
    repository.progress(job["job_id"], attempt["attempt_id"], stage, stage)
    repository.finish(
        job["job_id"], attempt["attempt_id"], success=success, stage=stage,
        history_event={
            "operation_id": attempt["attempt_id"], "woo_product_id": job["woo_product_id"],
            "source": "UltraPackV2", "previous_version": "2.3.2.1", "new_version": "2.3.4",
        },
    )
    return job, attempt


def test_success_creates_one_persistent_event_for_correct_product(tmp_path):
    repository = UpdateRepository(tmp_path)
    job, attempt = event(repository)
    stored = repository.history_event(attempt["attempt_id"])
    assert stored["woo_product_id"] == job["woo_product_id"]
    assert (stored["previous_version"], stored["new_version"]) == ("2.3.2.1", "2.3.4")
    assert UpdateRepository(tmp_path).history_event(attempt["attempt_id"])["operation_id"] == attempt["attempt_id"]


def test_rollback_or_error_never_creates_completed_history(tmp_path):
    repository = UpdateRepository(tmp_path)
    _job, attempt = event(repository, success=False, stage="rolled_back")
    assert repository.history_event(attempt["attempt_id"]) is None


def test_send_is_idempotent_and_readback_confirms_persistence(tmp_path):
    repository = UpdateRepository(tmp_path)
    _job, attempt = event(repository)
    client = HistoryClient()
    sync = UpdateHistorySynchronizer(repository, client)
    assert sync.sync_event(attempt["attempt_id"])["confirmed"] is True
    assert sync.sync_event(attempt["attempt_id"])["already_confirmed"] is True
    assert len(client.sent) == 1
    assert repository.history_event(attempt["attempt_id"])["sync_status"] == "confirmed"


def test_http_success_without_matching_persistence_is_detected(tmp_path):
    repository = UpdateRepository(tmp_path)
    _job, attempt = event(repository)
    result = UpdateHistorySynchronizer(repository, HistoryClient(persisted=False)).sync_event(attempt["attempt_id"])
    assert result["confirmed"] is False
    stored = repository.history_event(attempt["attempt_id"])
    assert stored["sync_status"] == "error" and "leitura posterior" in stored["sync_error"]


def test_confirmation_rejects_wrong_persisted_timestamp(tmp_path):
    repository = UpdateRepository(tmp_path)
    _job, attempt = event(repository)
    result = UpdateHistorySynchronizer(repository, HistoryClient(wrong_timestamp=True)).sync_event(attempt["attempt_id"])
    assert result["confirmed"] is False


def test_communication_error_stays_pending_for_retry_without_false_success(tmp_path):
    repository = UpdateRepository(tmp_path)
    _job, attempt = event(repository)
    result = UpdateHistorySynchronizer(repository, HistoryClient(fail=True)).sync_event(attempt["attempt_id"])
    assert result["confirmed"] is False
    assert repository.history_event(attempt["attempt_id"])["sync_status"] == "error"
    assert len(repository.pending_history_events()) == 1


def test_backfill_only_materializes_attempts_that_reached_completed(tmp_path):
    repository = UpdateRepository(tmp_path)
    repository.materialize([approval()])
    job = repository.list()["items"][0]
    current = repository.begin_attempt(job["job_id"])
    repository.progress(job["job_id"], current["attempt_id"], "already_current", "sem escrita")
    repository.finish(job["job_id"], current["attempt_id"], success=True, stage="already_current")
    assert repository.backfill_history_events() == 0
    retry = repository.begin_attempt(job["job_id"])
    repository.progress(job["job_id"], retry["attempt_id"], "completed", "aplicada")
    repository.finish(job["job_id"], retry["attempt_id"], success=True, stage="completed")
    assert repository.backfill_history_events() == 1
    assert repository.history_event(retry["attempt_id"])["sync_status"] == "pending"
