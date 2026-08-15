from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.operations.runtime_repair import completion_evidence, repair_payload, repair_update_runtime


class UpdateRuntimeRepairTests(unittest.TestCase):
    def _valid_job(self) -> dict:
        return {
            "job_id": "JOB-1",
            "woo_product_id": 123,
            "name": "Produto",
            "state": "completed",
            "effective_source_version": "2.0.0",
            "completed_at": "2026-08-14T20:00:00+00:00",
            "last_completed_step": "pt_versao_updated",
            "new_sha256": "b" * 64,
            "version_write_evidence": {"get_pt_versao": "2.0.0"},
            "execution_history": [],
            "diagnostics": [],
        }

    def _valid_plan(self) -> dict:
        return {
            "ready": True,
            "job_id": "JOB-1",
            "woo_product_id": 123,
            "new_zip": {"sha256": "b" * 64},
        }

    def test_valid_completion_is_preserved(self) -> None:
        job = self._valid_job()
        plan = self._valid_plan()
        self.assertTrue(completion_evidence(job, plan)["ok"])

        repaired, changes = repair_payload({"jobs": [job], "plans": {"JOB-1": plan}})
        self.assertEqual(changes, [])
        self.assertEqual(repaired["jobs"][0]["state"], "completed")

    def test_completion_without_remote_confirmation_is_quarantined(self) -> None:
        job = self._valid_job()
        job["version_write_evidence"] = {}
        plan = self._valid_plan()

        repaired, changes = repair_payload({"jobs": [job], "plans": {"JOB-1": plan}})
        item = repaired["jobs"][0]

        self.assertEqual(len(changes), 1)
        self.assertEqual(item["state"], "blocked")
        self.assertEqual(item["completed_at"], "")
        self.assertIn("quarentena", item["execution_error"].lower())
        self.assertEqual(item["execution_history"][-1]["result"], "completion_quarantined")
        self.assertIn("version_confirmed", item["execution_history"][-1]["failed_checks"])

    def test_prepared_jobs_are_never_changed(self) -> None:
        job = self._valid_job()
        job["state"] = "prepared"
        job["version_write_evidence"] = {}

        repaired, changes = repair_payload({"jobs": [job], "plans": {}})
        self.assertEqual(changes, [])
        self.assertEqual(repaired["jobs"][0]["state"], "prepared")

    def test_runtime_file_is_rewritten_atomically_when_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update_runtime.json"
            job = self._valid_job()
            job["new_sha256"] = ""
            payload = {"jobs": [job], "plans": {"JOB-1": self._valid_plan()}}
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = repair_update_runtime(path)
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(result["changed"], 1)
            self.assertEqual(saved["jobs"][0]["state"], "blocked")
            self.assertFalse(path.with_suffix(path.suffix + ".repair.tmp").exists())


if __name__ == "__main__":
    unittest.main()
