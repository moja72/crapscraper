from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import comparison_decisions, settings
from app.operations.queue import materialize_queue
from app.operations.models import JobState, OperationalJob, record_execution_outcome
from app.operations.cleanup_policy import build_cleanup_plan
from app.operations import runtime
from app.operations.update_logging import UpdateLogRegistry
from app.web import _build_update_preparation_service


SNAPSHOT = {
    "comparison_item_id": "restart-89416",
    "decision": "approve_update",
    "site_id": "89416",
    "woo_product_id": "89416",
    "site_name": "BeTheme",
    "site_version": "27.5.1",
    "site_product_url": "https://plugintema.example/betheme",
    "source_name": "Betheme",
    "source_version": "27.6.0",
    "source_product_url": "https://ultrapack.example/betheme",
    "source_official_url": "https://muffingroup.com/betheme/",
    "relationship_state": "safe_auto",
    "relationship_label": "Vinculo automatico seguro",
    "status": "update_available",
    "recommended_action": "review_and_approve_update",
}


class UpdatePersistenceTests(unittest.TestCase):
    def test_completed_survives_restart_with_canonical_history(self) -> None:
        runtime_path = Path(self.tmp.name) / "completed-runtime.json"
        job = OperationalJob("done", 94567, "BeTheme", "28.4.1.1", "28.5.6", "u", "",
                             "approve_update", "manual_confirmed", "update", job_id="DONE")
        job.state = JobState.COMPLETED
        job.effective_source_version = "28.5.7"
        job.prepared_at = "prepared"; job.executing_at = "executing"; job.completed_at = "completed"
        job.last_completed_step = "pt_versao_updated"
        plan = {"job_id": "DONE", "plan_id": "PLAN-DONE", "site_version": "28.4.1.1",
                "current_zip": {"sha256": "a" * 64, "remote_path": "/downloads/betheme.zip"},
                "new_zip": {"sha256": "b" * 64},
                "backup": {"path": "/downloads/betheme.zip.crapscraper.DONE.bak"},
                "remote_staging": {"upload_path": "/downloads/betheme.zip.crapscraper.DONE.upload"}}
        old_jobs, old_previews, old_plans = dict(runtime._JOBS), dict(runtime._PREVIEWS), dict(runtime._PLANS)
        try:
            with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
                runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
                runtime._JOBS[job.job_id] = job; runtime._PLANS[job.job_id] = plan
                runtime._persist(); runtime._JOBS.clear(); runtime._PLANS.clear(); runtime.restore()
                restored = runtime.get_job("DONE")
            self.assertEqual(restored.state, JobState.COMPLETED)
            self.assertEqual(restored.execution_history[-1]["result"], "completed")
            self.assertEqual(restored.execution_history[-1]["approved_source_version"], "28.5.6")
            self.assertEqual(restored.execution_history[-1]["effective_source_version"], "28.5.7")
        finally:
            runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
            runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(old_previews)
            runtime._PLANS.clear(); runtime._PLANS.update(old_plans)

    def test_completed_refresh_stays_completed_but_newer_approval_opens_new_cycle(self) -> None:
        old_jobs, old_previews, old_plans = dict(runtime._JOBS), dict(runtime._PREVIEWS), dict(runtime._PLANS)
        try:
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            completed = OperationalJob("cycle", 94567, "BeTheme", "28.4.1.1", "28.5.6", "u", "",
                                       "approve_update", "manual_confirmed", "update", job_id="OLD")
            completed.state = JobState.COMPLETED
            completed.effective_source_version = "28.5.7"
            runtime._JOBS[completed.job_id] = completed
            same = OperationalJob("cycle", 94567, "BeTheme", "28.5.7", "28.5.7", "u", "",
                                  "approve_update", "manual_confirmed", "update")
            with patch("app.operations.runtime.materialize_queue", return_value={"update": [same], "new_product": []}), \
                    patch.object(runtime, "_persist"):
                jobs = runtime.materialize([])
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["state"], "completed")
            self.assertEqual(jobs[0]["job_id"], "OLD")

            future = OperationalJob("cycle", 94567, "BeTheme", "28.5.7", "28.5.8", "u", "",
                                    "approve_update", "manual_confirmed", "update")
            with patch("app.operations.runtime.materialize_queue", return_value={"update": [future], "new_product": []}), \
                    patch.object(runtime, "_persist"):
                jobs = runtime.materialize([])
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["state"], "approved")
            self.assertNotEqual(jobs[0]["job_id"], "OLD")
            self.assertEqual(jobs[0]["approved_source_version"], "28.5.8")
        finally:
            runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
            runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(old_previews)
            runtime._PLANS.clear(); runtime._PLANS.update(old_plans)

    def test_history_excludes_secrets_and_cleanup_is_only_planned(self) -> None:
        job = OperationalJob("safe", 94567, "BeTheme", "1", "2", "u", "",
                             "approve_update", "manual_confirmed", "update", job_id="SAFE")
        job.state = JobState.COMPLETED; job.effective_source_version = "2"
        plan = {"job_id": "SAFE", "plan_id": "PLAN", "site_version": "1",
                "consumer_secret": "never-store-me", "authorization": "secret-header",
                "current_zip": {"remote_path": "/downloads/betheme.zip", "sha256": "a" * 64},
                "new_zip": {"sha256": "b" * 64},
                "backup": {"path": "/downloads/betheme.zip.crapscraper.SAFE.bak"},
                "remote_staging": {"upload_path": "/downloads/betheme.zip.crapscraper.SAFE.upload",
                                   "prepared_path": "/downloads/betheme.zip.crapscraper.SAFE.new"}}
        record_execution_outcome(job, plan, "completed")
        self.assertNotIn("never-store-me", repr(job.execution_history))
        self.assertNotIn("secret-header", repr(job.execution_history))
        cleanup = build_cleanup_plan(job, plan)
        self.assertTrue(cleanup["ready"])
        self.assertFalse(cleanup["execution_enabled"])
        self.assertFalse(cleanup["automatic"])
        self.assertEqual(cleanup["backup_preserved"], plan["backup"]["path"])
        self.assertNotIn(plan["current_zip"]["remote_path"], [x["path"] for x in cleanup["would_remove"]])
        self.assertNotIn(plan["backup"]["path"], [x["path"] for x in cleanup["would_remove"]])

    def test_ui_and_route_share_execution_eligibility_matrix(self) -> None:
        local_zip = Path(self.tmp.name) / "betheme.zip"
        local_zip.write_bytes(b"prepared")
        job = OperationalJob(
            "eligibility", 94567, "BeTheme", "28.4.1.1", "28.5.6",
            "https://example.test/source", "", "approve_update",
            "manual_confirmed", "update", job_id="ELIGIBLE",
        )
        preview = {"ready": True}
        backup = "/home/plugintema.com/downloads/betheme.zip.crapscraper.ELIGIBLE.bak"
        plan = {
            "ready": True, "job_id": job.job_id, "woo_product_id": 94567,
            "new_zip": {"local_staging_path": str(local_zip)},
            "backup": {"path": backup},
        }
        allowed = frozenset({94567})

        job.state = JobState.PLAN_READY
        self.assertTrue(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))

        job.state = JobState.ERROR
        job.last_completed_step = "backup_validated"
        job.backup_path = backup
        self.assertTrue(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))

        job.last_completed_step = ""
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))
        job.last_completed_step = "backup_validated"
        job.backup_path = backup + ".other"
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))
        job.backup_path = backup
        job.relationship = "pending_review"
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))
        job.relationship = "manual_confirmed"
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=False, allowed_product_ids=allowed
        ))
        job.woo_product_id = 12345
        plan["woo_product_id"] = 12345
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=allowed
        ))

    def test_astra_eligibility_requires_both_general_flag_and_whitelist(self) -> None:
        local_zip = Path(self.tmp.name) / "astra.zip"
        local_zip.write_bytes(b"prepared")
        job = OperationalJob("astra", 90109, "Astra WordPress Theme", "4.13.1", "4.13.9",
                             "u", "", "approve_update", "safe_auto", "update", job_id="ASTRA")
        job.state = JobState.PLAN_READY
        preview = {"ready": True}
        plan = {"ready": True, "job_id": "ASTRA", "woo_product_id": 90109,
                "new_zip": {"local_staging_path": str(local_zip)},
                "backup": {"path": "/downloads/astra.zip.crapscraper.ASTRA.bak"}}
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=frozenset({94567})
        ))
        self.assertTrue(runtime.is_execution_eligible(
            job, preview, plan, enabled=True, allowed_product_ids=frozenset({94567, 90109})
        ))
        self.assertFalse(runtime.is_execution_eligible(
            job, preview, plan, enabled=False, allowed_product_ids=frozenset({94567, 90109})
        ))

    def test_execution_failure_evidence_survives_restart(self) -> None:
        job = OperationalJob(
            "failure-evidence", 94567, "BeTheme", "28.4.1.1", "28.5.6",
            "https://example.test/source", "", "approve_update",
            "manual_confirmed", "update", job_id="FAILURE-EVIDENCE",
        )
        job.state = JobState.ERROR
        job.last_completed_step = "backup_validated"
        job.backup_path = "/home/plugintema.com/downloads/x.bak"
        job.execution_error = "Permission denied"
        job.version_write_evidence = {
            "http_status": 200, "put_pt_versao": "28.5.7",
            "get_pt_versao": "28.4.1.1", "confirmation_status": "diverged",
        }
        job.execution_logs = ["[00:01:15] Falha na execução: Permission denied"]
        runtime_path = Path(self.tmp.name) / "runtime.json"
        old_jobs = dict(runtime._JOBS)
        old_previews = dict(runtime._PREVIEWS)
        old_plans = dict(runtime._PLANS)
        with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            runtime._JOBS[job.job_id] = job
            runtime._persist()
            runtime._JOBS.clear()
            runtime.restore()
            restored = runtime.get_job(job.job_id)
        runtime._JOBS.clear(); runtime._JOBS.update(old_jobs)
        runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(old_previews)
        runtime._PLANS.clear(); runtime._PLANS.update(old_plans)
        self.assertEqual(restored.state, JobState.ERROR)
        self.assertEqual(restored.last_completed_step, "backup_validated")
        self.assertEqual(restored.backup_path, job.backup_path)
        self.assertEqual(restored.execution_error, "Permission denied")
        self.assertEqual(restored.version_write_evidence, job.version_write_evidence)
        self.assertEqual(restored.execution_logs, job.execution_logs)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "decisions.sqlite3"
        self.path_patch = patch.object(settings, "COMPARISON_DECISIONS_DB_PATH", self.db)
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_approve_update_snapshot_survives_restart_without_comparison_rows(self) -> None:
        saved = comparison_decisions.save_decision(**SNAPSHOT)
        self.assertEqual(saved["queue_type"], "update")
        self.assertEqual(saved["source_product_url"], SNAPSHOT["source_product_url"])

        # A fresh materialization reads SQLite only, as after a process restart.
        jobs = materialize_queue(comparison_rows=[])["update"]
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.woo_product_id, 89416)
        self.assertEqual(job.name, "BeTheme")
        self.assertEqual(job.plugintema_version, "27.5.1")
        self.assertEqual(job.ultrapack_version, "27.6.0")
        self.assertEqual(job.approved_source_version, "27.6.0")
        self.assertEqual(job.effective_source_version, "")
        self.assertEqual(job.ultrapack_url, SNAPSHOT["source_product_url"])
        self.assertEqual(job.relationship, "safe_auto")
        self.assertEqual(job.queue_type, "update")

    def test_additive_migration_keeps_legacy_decision_and_allows_fallback(self) -> None:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE comparison_decisions (comparison_item_id TEXT PRIMARY KEY, "
                "decision TEXT NOT NULL, decision_label TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', "
                "operator TEXT NOT NULL DEFAULT '', site_id TEXT NOT NULL DEFAULT '', site_name TEXT NOT NULL DEFAULT '', "
                "source_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '', recommended_action TEXT NOT NULL DEFAULT '', "
                "queue_type TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO comparison_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("legacy", "approve_update", "ok", "", "", "89416", "", "", "", "", "update", "now", "now"),
            )
        comparison_decisions.initialize_database()
        legacy = comparison_decisions.list_approved_updates()[0]
        self.assertIn("source_version", legacy)
        jobs = materialize_queue(
            comparison_rows=[{"comparison_item_id": "legacy", "site_name": "Legacy", "site_version": "1", "source_version": "2"}]
        )["update"]
        self.assertEqual(jobs[0].name, "Legacy")
        self.assertEqual(jobs[0].ultrapack_version, "2")

    def test_snapshot_does_not_persist_unrecognized_secret(self) -> None:
        saved = comparison_decisions.save_decision(**SNAPSHOT, password="never-store-me")
        self.assertNotIn("password", saved)
        self.assertNotIn("never-store-me", repr(saved))

    def test_executing_job_after_restart_becomes_interrupted(self) -> None:
        runtime_path = Path(self.tmp.name) / "update-runtime.json"
        job = OperationalJob("restart", 94567, "BeTheme", "28.4.1.1", "28.5.6",
                             "https://example/betheme", "", "approve_update",
                             "manual_confirmed", "update", job_id="RESTART-JOB")
        job.state = JobState.EXECUTING
        with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            runtime.persist_job(job)
            runtime._JOBS.clear()
            runtime.restore()
            restored = runtime.get_job("RESTART-JOB")
        self.assertEqual(restored.state, JobState.INTERRUPTED)
        self.assertIn("revalidação manual", restored.diagnostics[-1])

    def test_partial_invalid_and_unknown_runtime_fields_are_safe(self) -> None:
        runtime_path = Path(self.tmp.name) / "update-runtime.json"
        with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            runtime_path.write_text('{"jobs":', encoding="utf-8")
            runtime.restore()
            self.assertEqual(runtime._JOBS, {})
            legacy = OperationalJob("legacy", 94567, "BeTheme", "1", "2", "u", "",
                                    "approve_update", "manual_confirmed", "update", job_id="LEGACY")
            runtime.persist_job(legacy)
            payload = runtime_path.read_text(encoding="utf-8")
            self.assertNotEqual(payload.strip(), "")
            data = __import__("json").loads(payload)
            data["jobs"][0]["future_unknown"] = "ignored"
            runtime_path.write_text(__import__("json").dumps(data), encoding="utf-8")
            runtime._JOBS.clear(); runtime.restore()
            self.assertEqual(runtime.get_job("LEGACY").state, JobState.APPROVED)

    def test_new_prepare_invalidates_old_plan(self) -> None:
        runtime_path = Path(self.tmp.name) / "update-runtime.json"
        with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            job = OperationalJob("p", 94567, "BeTheme", "1", "2", "u", "",
                                 "approve_update", "manual_confirmed", "update", job_id="PLAN")
            runtime.persist_job(job)
            runtime.save_plan(job.job_id, {"plan_id": "old"})
            runtime.save_preview(job.job_id, {"ready": True})
            with self.assertRaises(KeyError): runtime.get_plan(job.job_id)

    def test_successful_new_prepare_archives_old_error_and_clears_active_evidence(self) -> None:
        runtime_path = Path(self.tmp.name) / "update-runtime.json"
        with patch.object(settings, "UPDATE_RUNTIME_PATH", runtime_path):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            job = OperationalJob("history", 94567, "BeTheme", "1", "2", "u", "",
                                 "approve_update", "manual_confirmed", "update", job_id="HISTORY")
            job.state = JobState.PREPARED
            job.execution_error = "old failure"
            job.execution_logs = ["old execution log"]
            job.version_write_evidence = {"confirmation_status": "diverged"}
            job.last_completed_step = "production_zip_installed"
            runtime.persist_job(job)
            runtime.save_preview(job.job_id, {"ready": True})
            current = runtime.get_job(job.job_id)
            self.assertEqual(current.execution_error, "")
            self.assertEqual(current.execution_logs, [])
            self.assertEqual(current.version_write_evidence, {})
            self.assertEqual(current.last_completed_step, "")
            self.assertEqual(len(current.execution_history), 1)
            self.assertEqual(current.execution_history[0]["error"], "old failure")
            runtime._JOBS.clear(); runtime.restore()
            restored = runtime.get_job(job.job_id)
            self.assertEqual(restored.execution_error, "")
            self.assertEqual(restored.execution_history[0]["logs"], ["old execution log"])

    def test_failed_new_prepare_does_not_archive_or_clear_old_error(self) -> None:
        job = OperationalJob("history-fail", 94567, "BeTheme", "1", "2", "u", "",
                             "approve_update", "manual_confirmed", "update", job_id="HISTORY-FAIL")
        job.execution_error = "keep me"
        runtime._JOBS[job.job_id] = job
        self.assertEqual(job.execution_error, "keep me")
        self.assertEqual(job.execution_history, [])

    def test_logs_are_isolated_by_job(self) -> None:
        registry = UpdateLogRegistry()
        registry.for_job("A").log("job A")
        registry.for_job("B").log("job B")
        self.assertIn("job A", registry.to_list("A")[0])
        self.assertNotIn("job B", " ".join(registry.to_list("A")))


class BuilderConfigurationTests(unittest.TestCase):
    @patch("app.integrations.ssh_storage.ReadOnlySSHStorage.from_env")
    @patch("app.web.os.getenv")
    def test_builder_uses_existing_wp_and_wc_variables(self, getenv: Mock, storage_from_env: Mock) -> None:
        values = {
            "SCRAPER_WP_BASE_URL": "https://example.test",
            "SCRAPER_WC_CONSUMER_KEY": "ck_test",
            "SCRAPER_WC_CONSUMER_SECRET": "cs_test",
        }
        getenv.side_effect = lambda name, default="": values.get(name, default)
        storage_from_env.return_value.connect.return_value = SimpleNamespace(_client=None)
        service = _build_update_preparation_service(SimpleNamespace(ultrapack_http_session=Mock()))
        self.assertEqual(service.woo.base_url, values["SCRAPER_WP_BASE_URL"])
        self.assertEqual(service.woo.username, values["SCRAPER_WC_CONSUMER_KEY"])
        self.assertEqual(service.woo.password, values["SCRAPER_WC_CONSUMER_SECRET"])
        requested = {call.args[0] for call in getenv.call_args_list}
        self.assertNotIn("SCRAPER_WC_BASE_URL", requested)
        self.assertNotIn("SCRAPER_WC_USERNAME", requested)
        self.assertNotIn("SCRAPER_WC_PASSWORD", requested)

    def test_builder_error_never_contains_secret(self) -> None:
        env = {
            "SCRAPER_WP_BASE_URL": "",
            "SCRAPER_WC_CONSUMER_KEY": "ck_visible_only_to_test",
            "SCRAPER_WC_CONSUMER_SECRET": "cs_must_not_leak",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as caught:
                _build_update_preparation_service(SimpleNamespace(ultrapack_http_session=Mock()))
        self.assertNotIn(env["SCRAPER_WC_CONSUMER_SECRET"], str(caught.exception))


if __name__ == "__main__":
    unittest.main()
