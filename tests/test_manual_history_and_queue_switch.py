from __future__ import annotations

import unittest
from unittest.mock import patch

from app.operations import runtime
from app.operations.models import JobState, OperationalJob


def job(job_id: str, state: JobState, *, queue: str = "Manual") -> OperationalJob:
    item = OperationalJob(
        comparison_item_id=f"cmp-{job_id}", woo_product_id=92038,
        name="Elementor Pro", plugintema_version="4.0.4",
        ultrapack_version="4.2.1", ultrapack_url="https://ultrapackv2.com/item",
        official_url="https://elementor.com/pro/", decision="approve_update",
        relationship="safe_auto", queue_type="update", approved_source_version="4.2.1",
        job_id=job_id, source_name="UltraPackV2",
        initiated_by="wordpress-super-admin #1", manual_requested_at="2026-08-16T20:00:00+00:00",
    )
    item.queue_name = queue
    item.state = state
    item.completed_at = "2026-08-16T20:05:00+00:00"
    return item


class ManualHistoryAndQueueSwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = dict(runtime._JOBS)
        self.queues = dict(runtime._QUEUE_CONTROL)
        runtime._JOBS.clear()
        runtime._QUEUE_CONTROL.clear()
        runtime._QUEUE_CONTROL.update({"status": "stopped", "active_queue": "default",
                                       "queues": {"default": {}, "Manual": {}}})

    def tearDown(self) -> None:
        runtime._JOBS.clear()
        runtime._JOBS.update(self.jobs)
        runtime._QUEUE_CONTROL.clear()
        runtime._QUEUE_CONTROL.update(self.queues)

    def test_completed_and_error_manual_jobs_use_normal_history(self) -> None:
        completed = job("manual-completed", JobState.COMPLETED)
        failed = job("manual-error", JobState.ERROR)
        failed.execution_error = "Falha sanitizada"
        runtime._JOBS.update({completed.job_id: completed, failed.job_id: failed})
        rows = runtime.history_jobs()
        self.assertEqual({row["state"] for row in rows}, {"completed", "error"})
        for row in rows:
            self.assertEqual(row["queue_name"], "Manual")
            self.assertEqual(row["initiated_by"], "wordpress-super-admin #1")
            self.assertTrue(row["manual_requested_at"])

    def test_selecting_queue_with_terminal_items_returns_its_details(self) -> None:
        completed = job("manual-completed", JobState.COMPLETED)
        runtime._JOBS[completed.job_id] = completed
        with patch.object(runtime, "_persist"):
            snapshot = runtime.select_update_queue("Manual")
        details = runtime.update_queue_details("Manual")
        self.assertEqual(snapshot["active_queue"], "Manual")
        self.assertEqual(details["queue"]["total"], 1)
        self.assertEqual(details["items"][0]["job_id"], completed.job_id)

    def test_materialization_does_not_absorb_manual_history(self) -> None:
        manual = job("manual-completed", JobState.COMPLETED)
        normal = job("normal-new", JobState.APPROVED, queue="default")
        normal.comparison_item_id = manual.comparison_item_id
        runtime._JOBS[manual.job_id] = manual
        with patch("app.operations.runtime.materialize_queue", return_value={"update": [normal], "addition": []}), \
             patch.object(runtime, "_persist"):
            runtime.materialize([])
        self.assertIn(manual.job_id, runtime._JOBS)
        self.assertIn(normal.job_id, runtime._JOBS)


if __name__ == "__main__":
    unittest.main()
