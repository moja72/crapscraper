from __future__ import annotations

import unittest
from types import SimpleNamespace

import app.update_prepare_plan_reliability_policy as policy


class UpdatePreparePlanReliabilityPolicyTests(unittest.TestCase):
    def _preview(self, approved: str, effective: str = "2.36.0") -> dict:
        return {
            "ready": True,
            "versions": {
                "site_version": "2.35.4",
                "approved_source_version": approved,
                "effective_source_version": effective,
                "ultrapack_approved": approved,
            },
            "new_zip": {"sha256": "a" * 64, "path": "C:/tmp/affiliatewp.zip"},
        }

    def test_reconciles_polluted_job_snapshot_to_older_preview_snapshot(self) -> None:
        job = SimpleNamespace(
            approved_source_version="2.36.0",
            effective_source_version="2.36.0",
        )
        preview, changed = policy._reconcile_approved_snapshot(
            job, self._preview("2.35.2")
        )
        self.assertTrue(changed)
        self.assertEqual(job.approved_source_version, "2.35.2")
        self.assertEqual(preview["versions"]["approved_source_version"], "2.35.2")
        self.assertEqual(preview["versions"]["effective_source_version"], "2.36.0")

    def test_reconciles_polluted_preview_snapshot_to_older_job_snapshot(self) -> None:
        job = SimpleNamespace(
            approved_source_version="2.35.2",
            effective_source_version="2.36.0",
        )
        preview, changed = policy._reconcile_approved_snapshot(
            job, self._preview("2.36.0")
        )
        self.assertTrue(changed)
        self.assertEqual(job.approved_source_version, "2.35.2")
        self.assertEqual(preview["versions"]["approved_source_version"], "2.35.2")
        self.assertEqual(preview["versions"]["ultrapack_approved"], "2.35.2")

    def test_does_not_reconcile_snapshot_newer_than_effective_source(self) -> None:
        job = SimpleNamespace(
            approved_source_version="2.40.0",
            effective_source_version="2.36.0",
        )
        preview, changed = policy._reconcile_approved_snapshot(
            job, self._preview("2.35.2")
        )
        self.assertFalse(changed)
        self.assertEqual(job.approved_source_version, "2.40.0")
        self.assertEqual(preview["versions"]["approved_source_version"], "2.35.2")

    def test_does_not_reconcile_if_effective_versions_disagree(self) -> None:
        job = SimpleNamespace(
            approved_source_version="2.36.0",
            effective_source_version="2.37.0",
        )
        preview, changed = policy._reconcile_approved_snapshot(
            job, self._preview("2.35.2", effective="2.36.0")
        )
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
