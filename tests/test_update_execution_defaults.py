from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.configuration import (
    DEFAULT_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
    parse_update_execution_allowed_product_ids,
)
from app.operations.models import JobState
import app.operational_simple_flow_execution_policy as policy


class UpdateExecutionDefaultTests(unittest.TestCase):
    def test_missing_allowlist_allows_all_products(self) -> None:
        self.assertEqual(DEFAULT_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS, frozenset())
        self.assertEqual(parse_update_execution_allowed_product_ids(None), frozenset())

    def test_explicit_allowlist_still_restricts_products(self) -> None:
        self.assertEqual(
            parse_update_execution_allowed_product_ids("94567, 90538"),
            frozenset({94567, 90538}),
        )
        self.assertEqual(parse_update_execution_allowed_product_ids("*"), frozenset())

    def _eligible_fixture(self, local_path: str):
        job = SimpleNamespace(
            job_id="job_advanced_ads",
            woo_product_id=90538,
            state=JobState.PLAN_READY,
            last_completed_step="",
            backup_path="/home/plugintema.com/downloads/a.zip.bak",
            relationship="safe_auto",
        )
        preview = {"ready": True}
        plan = {
            "ready": True,
            "job_id": job.job_id,
            "woo_product_id": job.woo_product_id,
            "backup": {"path": job.backup_path},
            "new_zip": {"local_staging_path": local_path},
        }
        return job, preview, plan

    def test_old_homologation_id_is_reported_when_explicitly_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "advanced-ads.zip"
            local.write_bytes(b"zip")
            job, preview, plan = self._eligible_fixture(str(local))
            with patch.object(policy.settings, "UPDATE_EXECUTION_ENABLED", True), patch.object(
                policy.settings,
                "UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS",
                frozenset({94567}),
            ):
                reasons = policy.execution_ineligibility_reasons(job, preview, plan)
        self.assertTrue(any("allowlist" in item and "94567" in item for item in reasons))

    def test_empty_allowlist_does_not_block_valid_selected_product(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "advanced-ads.zip"
            local.write_bytes(b"zip")
            job, preview, plan = self._eligible_fixture(str(local))
            with patch.object(policy.settings, "UPDATE_EXECUTION_ENABLED", True), patch.object(
                policy.settings,
                "UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS",
                frozenset(),
            ):
                reasons = policy.execution_ineligibility_reasons(job, preview, plan)
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
