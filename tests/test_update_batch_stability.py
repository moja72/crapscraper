from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.operations.runtime as runtime
import app.staging_reuse_policy as staging_reuse
import app.update_cross_source_latest_policy as latest_source
import app.update_prepare_plan_reliability_policy as policy
from app.operations.models import JobState, OperationalJob
from app.operations.preparation import _compare_source_version


NEW_SHA = "b" * 64


def make_job(*, state: JobState = JobState.DOWNLOADING) -> OperationalJob:
    job = OperationalJob(
        "batch-race-comparison", 95533, "Edubin", "9.5.12", "9.6.4",
        "https://plugintheme.net/product/edubin", "", "approve_update",
        "safe_auto", "update", job_id="BATCH-RACE-95533",
    )
    job.state = state
    return job


class UpdateBatchStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = dict(runtime._JOBS)
        self.previews = dict(runtime._PREVIEWS)
        self.plans = dict(runtime._PLANS)
        self.core_materialize = policy._BASE_CORE_MATERIALIZE
        runtime._JOBS.clear()
        runtime._PREVIEWS.clear()
        runtime._PLANS.clear()

    def tearDown(self) -> None:
        runtime._JOBS.clear()
        runtime._JOBS.update(self.jobs)
        runtime._PREVIEWS.clear()
        runtime._PREVIEWS.update(self.previews)
        runtime._PLANS.clear()
        runtime._PLANS.update(self.plans)
        policy._BASE_CORE_MATERIALIZE = self.core_materialize

    def test_polling_cannot_replace_job_used_by_active_batch_worker(self) -> None:
        original = make_job(state=JobState.DOWNLOADING)
        original.local_staging_path = "data/staging/updates/BATCH-RACE-95533/edubin.zip"
        original.new_sha256 = NEW_SHA
        runtime._JOBS[original.job_id] = original

        def destructive_materialize(_rows=()):
            replacement = make_job(state=JobState.DOWNLOADING)
            runtime._JOBS[replacement.job_id] = replacement
            return [runtime.job_public(replacement)]

        policy._BASE_CORE_MATERIALIZE = destructive_materialize
        with patch.object(runtime, "_persist", return_value=None):
            rows = policy._materialize_core_preserving_active(())

        self.assertIs(runtime._JOBS[original.job_id], original)
        self.assertEqual(runtime._JOBS[original.job_id].local_staging_path, original.local_staging_path)
        self.assertEqual(runtime._JOBS[original.job_id].new_sha256, NEW_SHA)
        self.assertEqual(rows[0]["job_id"], original.job_id)

    def test_ready_preview_restores_canonical_job_staging_before_plan(self) -> None:
        job = make_job(state=JobState.PREPARED)
        runtime._JOBS[job.job_id] = job
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "edubin.zip"
            local.write_bytes(b"PK\x03\x04test")
            preview = {
                "job_id": job.job_id,
                "ready": True,
                "versions": {"effective_source_version": "9.6.4"},
                "new_zip": {
                    "local_staging_path": str(local),
                    "sha256": NEW_SHA,
                },
            }
            changed = policy._sync_prepared_artifact(job.job_id, preview)

        self.assertTrue(changed)
        self.assertEqual(job.local_staging_path, str(local))
        self.assertEqual(job.new_sha256, NEW_SHA)
        self.assertEqual(job.effective_source_version, "9.6.4")

    def test_local_reuse_accepts_path_alias_and_equivalent_version(self) -> None:
        self.assertEqual(
            staging_reuse._artifact_path({"local_staging_path": "C:/staging/item.zip"}),
            "C:/staging/item.zip",
        )
        self.assertTrue(staging_reuse._same_version("1.2", "1.2.0"))
        self.assertFalse(staging_reuse._same_version("1.2", "1.3"))

    def test_live_source_newer_than_comparison_is_valid_upgrade_target(self) -> None:
        self.assertEqual(_compare_source_version("1.2", "1.1"), 1)
        self.assertTrue(latest_source._is_newer("1.2", "1.1"))


if __name__ == "__main__":
    unittest.main()
