from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.operations.execution_plan import build_execution_plan
from app.operations.models import JobState, OperationalJob
from app.operations.real_executor import ControlledUpdateExecutor
from app.integrations.wordpress import WriteOperationDisabledError
from tests.test_execution_plan import CURRENT_SHA, NEW_SHA, prepared_preview


class Woo:
    def __init__(self): self.version = "28.4.1.1"
    def get_product(self, _id): return {"id": 94567, "meta_data": [{"id": 1, "key": "pt_versao", "value": self.version}]}
    def list_variations(self, _id):
        remote = "/home/plugintema.com/downloads/BeTheme.zip"
        return [{"id": 89417, "downloadable": True, "downloads": [{"id":"download-a","name":"BeTheme","file":remote}]},
                {"id": 89418, "downloadable": True, "downloads": [{"id":"download-b","name":"BeTheme","file":remote}]}]


class Storage:
    def __init__(self, plan): self.hashes = {plan["current_zip"]["remote_path"]: CURRENT_SHA}
    def sha256(self, path): return self.hashes[path]
    def exists(self, path): return path in self.hashes


class Staging:
    def __init__(self, storage, plan, fail_upload=False):
        self.storage, self.plan, self.fail_upload, self.chmod_calls = storage, plan, fail_upload, []
    def upload_staging(self, source):
        if self.fail_upload: raise PermissionError("Permission denied password=secret")
        source.read(); path = self.plan["remote_staging"]["upload_path"]
        self.storage.hashes[path] = self.plan["new_zip"]["sha256"]; return path
    def sha256(self, path): return self.storage.sha256(path)
    def exists(self, path): return self.storage.exists(path)
    def chmod_staging_upload(self, path): self.chmod_calls.append(path)


class Helper:
    def __init__(self, storage, plan, fail=""): self.storage, self.plan, self.calls, self.fail = storage, plan, [], fail
    def invoke(self, request):
        self.calls.append(request.operation)
        if self.fail == request.operation: raise RuntimeError("injected " + request.operation)
        if request.operation == "backup": self.storage.hashes[self.plan["backup"]["path"]] = CURRENT_SHA
        if request.operation == "install": self.storage.hashes[self.plan["current_zip"]["remote_path"]] = self.plan["new_zip"]["sha256"]
        if request.operation == "rollback": self.storage.hashes[self.plan["current_zip"]["remote_path"]] = CURRENT_SHA
        return {"ok": True, "operation": request.operation}


class Writer:
    def __init__(self, woo, fail_apply=False): self.woo, self.fail_apply, self.calls = woo, fail_apply, []
    def prepare(self, product_id, old, new): self.calls.append("prepare"); return (old, new)
    def apply(self, plan):
        self.calls.append("apply")
        if self.fail_apply: raise RuntimeError("write failed")
        self.woo.version = plan[1]
    def rollback(self, plan): self.calls.append("rollback"); self.woo.version = plan[0]
    def apply_and_confirm(self, plan, rollback=False):
        if rollback:
            self.rollback(plan); value = plan[0]
        else:
            self.apply(plan); value = plan[1]
        return {"http_status": 200, "response_body_present": True,
                "product_id": 94567, "put_pt_versao": value, "put_meta_id": 1,
                "get_pt_versao": value, "get_meta_id": 1,
                "confirmation_status": "confirmed"}


def fixture(directory):
    job = OperationalJob("betheme", 94567, "BeTheme", "28.4.1.1", "28.5.6",
                         "https://example/betheme", "", "approve_update",
                         "manual_confirmed", "update", job_id="BETHEME-94567")
    job.effective_source_version = "28.5.7"; job.state = JobState.PREPARED
    preview = prepared_preview(); preview["product"]["id"] = 94567
    local = Path(directory) / "betheme.zip"; local.write_bytes(b"new zip")
    import hashlib
    digest = hashlib.sha256(local.read_bytes()).hexdigest()
    preview["new_zip"]["path"] = str(local); preview["new_zip"]["sha256"] = digest
    plan = build_execution_plan(job, preview); plan["new_zip"]["sha256"] = digest
    for item in plan["preconditions"]:
        if item["key"] == "local_zip_sha256": item["expected"] = digest
    return job, plan, digest


class RealExecutionTests(unittest.TestCase):
    def make(self, directory, **kwargs):
        job, plan, digest = fixture(directory)
        woo = Woo(); storage = Storage(plan); staging = Staging(storage, plan, kwargs.get("fail_upload", False)); helper = Helper(storage, plan, kwargs.get("fail_helper", "")); writer = Writer(woo, kwargs.get("fail_apply", False))
        executor = ControlledUpdateExecutor(woo, storage, staging, helper, writer,
                                            enabled=kwargs.get("enabled", True), allowed_product_ids=frozenset({94567}),
                                            fault=kwargs.get("fault"))
        return job, plan, woo, storage, staging, helper, writer, executor, digest

    def test_disabled_by_default_guard(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, *_rest, executor, _ = self.make(d, enabled=False)
            with self.assertRaises(WriteOperationDisabledError): executor.execute(job, plan, "EXECUTAR 94567")

    def test_confirmation_plan_and_whitelist_guards(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, *_rest, executor, _ = self.make(d)
            with self.assertRaises(PermissionError): executor.execute(job, plan, "EXECUTAR")
            other = dict(plan); other["job_id"] = "OTHER"
            with self.assertRaises(PermissionError): executor.execute(job, other, "EXECUTAR 94567")
            job.woo_product_id = 1
            with self.assertRaises(PermissionError): executor.execute(job, plan, "EXECUTAR 1")

    def test_unsafe_relationship_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, *_rest, executor, _ = self.make(d); job.relationship = "pending_review"
            with self.assertRaises(ValueError): executor.execute(job, plan, "EXECUTAR 94567")

    def test_precondition_changes_block_before_writes(self):
        for change in ("version", "remote", "missing", "local"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                job, plan, woo, storage, _staging, helper, writer, executor, _ = self.make(d)
                if change == "version": woo.version = "changed"
                elif change == "remote": storage.hashes[plan["current_zip"]["remote_path"]] = "c"*64
                elif change == "missing": Path(plan["new_zip"]["local_staging_path"]).unlink()
                else: Path(plan["new_zip"]["local_staging_path"]).write_bytes(b"changed")
                with self.assertRaises(ValueError): executor.execute(job, plan, "EXECUTAR 94567")
                self.assertEqual(helper.calls, []); self.assertNotIn("apply", writer.calls)
                self.assertEqual(job.state, JobState.BLOCKED)

    def test_success_orders_backup_staging_install_and_updates_effective(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, woo, storage, staging, helper, writer, executor, _ = self.make(d)
            executor.execute(job, plan, "EXECUTAR 94567")
            self.assertEqual(helper.calls, ["backup", "prepare", "install"])
            self.assertEqual(woo.version, "28.5.7")
            self.assertEqual(job.approved_source_version, "28.5.6")
            self.assertEqual(job.state, JobState.COMPLETED)
            self.assertEqual(job.execution_history[-1]["result"], "completed")
            self.assertEqual(job.execution_history[-1]["effective_source_version"], "28.5.7")
            self.assertEqual(storage.hashes[plan["backup"]["path"]], CURRENT_SHA)
            self.assertEqual(staging.chmod_calls, [plan["remote_staging"]["upload_path"]])

    def test_backup_failure_prevents_staging_install_and_version_write(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, woo, _s, _staging, helper, writer, executor, _ = self.make(d, fail_helper="backup")
            with self.assertRaises(RuntimeError): executor.execute(job, plan, "EXECUTAR 94567")
            self.assertEqual(helper.calls, ["backup"]); self.assertNotIn("apply", writer.calls)

    def test_failure_after_swap_rolls_back_zip_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, woo, storage, _staging, helper, writer, executor, _ = self.make(d, fail_apply=True)
            with self.assertRaises(RuntimeError): executor.execute(job, plan, "EXECUTAR 94567")
            self.assertIn("rollback", helper.calls); self.assertEqual(woo.version, "28.4.1.1")
            self.assertEqual(storage.hashes[plan["current_zip"]["remote_path"]], CURRENT_SHA)
            self.assertEqual(job.state, JobState.ROLLED_BACK)

    def test_download_order_is_semantically_irrelevant(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, woo, _storage, _staging, _helper, _writer, executor, _ = self.make(d)
            original = woo.list_variations
            woo.list_variations = lambda product_id: list(reversed(original(product_id)))
            result = executor.execute(job, plan, "EXECUTAR 94567")
            self.assertTrue(result["ok"])

    def test_rollback_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, _woo, _storage, _staging, helper, _writer, executor, _ = self.make(
                d, fail_apply=True, fail_helper="rollback"
            )
            with self.assertRaises(RuntimeError): executor.execute(job, plan, "EXECUTAR 94567")
            self.assertIn("rollback", helper.calls)
            self.assertEqual(job.state, JobState.ROLLBACK_REQUIRED)

    def test_faults_preserve_transaction_invariants_at_each_boundary(self):
        for stage, should_rollback in (("after_backup", False), ("after_staging", False),
                                       ("after_install", True), ("after_pt_versao", True)):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as d:
                def fault(value):
                    if value == stage: raise RuntimeError("injected " + stage)
                job, plan, woo, storage, _staging, helper, _writer, executor, _ = self.make(d, fault=fault)
                with self.assertRaises(RuntimeError): executor.execute(job, plan, "EXECUTAR 94567")
                self.assertEqual(storage.hashes[plan["current_zip"]["remote_path"]], CURRENT_SHA)
                self.assertEqual(woo.version, "28.4.1.1")
                if should_rollback:
                    self.assertIn("rollback", helper.calls)
                    self.assertEqual(job.state, JobState.ROLLED_BACK)
                else:
                    self.assertNotIn("install", helper.calls)
                    self.assertEqual(job.state, JobState.ERROR)

    def test_upload_failure_keeps_production_backup_and_evidence_without_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            logs = []
            job, plan, woo, storage, _staging, helper, writer, _executor, _ = self.make(d)
            executor = ControlledUpdateExecutor(
                woo, storage, Staging(storage, plan, fail_upload=True), helper, writer,
                enabled=True, allowed_product_ids=frozenset({94567}), logger=logs.append,
            )
            with self.assertRaises(PermissionError):
                executor.execute(job, plan, "EXECUTAR 94567")
            self.assertEqual(storage.sha256(plan["current_zip"]["remote_path"]), CURRENT_SHA)
            self.assertEqual(storage.sha256(plan["backup"]["path"]), CURRENT_SHA)
            self.assertEqual(woo.version, "28.4.1.1")
            self.assertNotIn("install", helper.calls)
            self.assertNotIn("rollback", helper.calls)
            self.assertEqual(job.last_completed_step, "backup_validated")
            self.assertEqual(job.state, JobState.ERROR)
            self.assertIn("[redacted]", job.execution_error)
            self.assertTrue(any("rollback não necessário" in entry for entry in logs))

    def test_retry_reuses_matching_backup_and_upload_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, woo, storage, staging, helper, writer, executor, _ = self.make(d)
            storage.hashes[plan["backup"]["path"]] = CURRENT_SHA
            storage.hashes[plan["remote_staging"]["upload_path"]] = plan["new_zip"]["sha256"]
            executor.execute(job, plan, "EXECUTAR 94567")
            self.assertEqual(helper.calls, ["prepare", "install"])
            self.assertEqual(staging.chmod_calls, [plan["remote_staging"]["upload_path"]])

    def test_retry_blocks_mismatched_existing_backup(self):
        with tempfile.TemporaryDirectory() as d:
            job, plan, _woo, storage, _staging, helper, _writer, executor, _ = self.make(d)
            storage.hashes[plan["backup"]["path"]] = "f" * 64
            with self.assertRaisesRegex(Exception, "Backup existente diverge"):
                executor.execute(job, plan, "EXECUTAR 94567")
            self.assertEqual(helper.calls, [])


if __name__ == "__main__": unittest.main()
