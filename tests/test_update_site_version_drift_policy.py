from __future__ import annotations

import unittest

from app.operations.models import JobState
from app.operations.preparation import UpdatePreview, ValidationItem
import app.update_site_version_drift_policy as policy


class _Job:
    def __init__(self, version: str = "2.32.1") -> None:
        self.plugintema_version = version
        self.current_sha256 = ""
        self.new_sha256 = ""
        self.local_staging_path = ""
        self.prepared_at = ""
        self.execution_error = "bloqueado"
        self.state = JobState.BLOCKED
        self.diagnostics: list[str] = []

    def set_state(self, state: JobState, message: str = "") -> None:
        self.state = state
        if message:
            self.diagnostics.append(message)


class _Service:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def logger(self, message: str) -> None:
        self.logs.append(message)


def _preview(*, current: str = "2.35.4", source: str = "2.36.0", other_failure: bool = False) -> UpdatePreview:
    validations = [
        ValidationItem("product", "Produto validado", True, "Woo #89674"),
        ValidationItem("relationship", "Vínculo validado", True, "safe_auto"),
        ValidationItem("version", "pt_versao validado", False, "esperado 2.32.1; atual 2.35.4", "error"),
        ValidationItem("downloads", "Downloads validados", not other_failure, "downloads"),
        ValidationItem("current_zip", "ZIP atual validado", True, "oldsha"),
        ValidationItem("ultrapack", "Produto da fonte validado", True, source),
        ValidationItem("downloaded", "Novo ZIP baixado", True, "C:/staging/AffiliateWP.zip"),
        ValidationItem("new_zip", "Novo ZIP válido", True, "newsha"),
        ValidationItem("backup", "Backup disponível", True, "snapshot"),
        ValidationItem("helper", "Helper disponível", True, "ok"),
        ValidationItem("execution", "Execução controlada disponível", True, "ok"),
    ]
    return UpdatePreview(
        job_id="job-affiliatewp",
        state="blocked",
        product={"id": 89674, "name": "AffiliateWP WordPress Plugin"},
        versions={
            "site_version": current,
            "approved_source_version": source,
            "effective_source_version": source,
        },
        current_zip={"sha256": "oldsha"},
        new_zip={"sha256": "newsha", "path": "C:/staging/AffiliateWP.zip"},
        variations=[89675, 89676],
        downloads=[{"file": "/home/plugintema.com/downloads/affiliate-wp.zip"}],
        physical_path="/home/plugintema.com/downloads/affiliate-wp.zip",
        rollback_snapshot={"pt_versao": current},
        validations=validations,
        execution_enabled=True,
    )


class UpdateSiteVersionDriftPolicyTests(unittest.TestCase):
    def test_affiliatewp_forward_drift_is_safe(self) -> None:
        self.assertTrue(policy._is_safe_forward_drift("2.35.4", "2.32.1", "2.36.0"))

    def test_forward_drift_repairs_preview_and_uses_live_site_version(self) -> None:
        service = _Service()
        job = _Job("2.32.1")
        preview = _preview()

        changed = policy._repair_safe_forward_drift(service, job, preview)

        self.assertTrue(changed)
        self.assertTrue(preview.ready)
        self.assertEqual(JobState.PREPARED, job.state)
        self.assertEqual("2.35.4", job.plugintema_version)
        self.assertEqual("oldsha", job.current_sha256)
        self.assertEqual("newsha", job.new_sha256)
        self.assertEqual("C:/staging/AffiliateWP.zip", job.local_staging_path)
        validation = next(item for item in preview.validations if item.key == "version")
        self.assertTrue(validation.ok)
        self.assertEqual("info", validation.level)
        self.assertIn("2.35.4", validation.detail)
        self.assertIn("2.36.0", validation.detail)

    def test_regression_is_not_accepted(self) -> None:
        self.assertFalse(policy._is_safe_forward_drift("2.31.0", "2.32.1", "2.36.0"))

    def test_already_current_is_not_treated_as_forward_drift(self) -> None:
        self.assertFalse(policy._is_safe_forward_drift("2.36.0", "2.32.1", "2.36.0"))
        self.assertFalse(policy._is_safe_forward_drift("2.37.0", "2.32.1", "2.36.0"))

    def test_other_failure_remains_blocking(self) -> None:
        service = _Service()
        job = _Job("2.32.1")
        preview = _preview(other_failure=True)
        self.assertFalse(policy._repair_safe_forward_drift(service, job, preview))
        self.assertFalse(preview.ready)
        self.assertEqual(JobState.BLOCKED, job.state)


if __name__ == "__main__":
    unittest.main()
