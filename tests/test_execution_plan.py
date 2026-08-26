from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from app import settings
from app.operations.execution_plan import build_execution_plan, evaluate_preconditions
from app.operations.models import JobState, OperationalJob


CURRENT_SHA = "a" * 64
NEW_SHA = "b" * 64


def prepared_job() -> OperationalJob:
    job = OperationalJob(
        "betheme-comparison", 89416, "BeTheme", "28.4.1.1", "28.5.6",
        "https://ultrapack.example/betheme", "", "approve_update",
        "manual_confirmed", "update", job_id="BETHEME-CONTROLLED-20260812",
    )
    job.effective_source_version = "28.5.7"
    job.state = JobState.PREPARED
    return job


def prepared_preview(*, ready: bool = True) -> dict:
    remote = "/home/plugintema.com/downloads/BeTheme.zip"
    downloads = [
        {"variation_id": 89417, "id": "download-a", "name": "BeTheme", "file": remote},
        {"variation_id": 89418, "id": "download-b", "name": "BeTheme", "file": remote},
    ]
    return {
        "ready": ready,
        "product": {"id": 89416, "name": "BeTheme"},
        "versions": {
            "site_version": "28.4.1.1",
            "approved_source_version": "28.5.6",
            "effective_source_version": "28.5.7",
        },
        "physical_path": remote,
        "current_zip": {"path": remote, "size": 100, "sha256": CURRENT_SHA,
                        "owner": "plugi2090", "group": "nobody", "mode": "-rw-rwxr--"},
        "new_zip": {"path": "data/staging/updates/BETHEME/new.zip", "file_name": "new.zip",
                    "size": 120, "sha256": NEW_SHA, "entries": 42},
        "variations": [89417, 89418],
        "downloads": downloads,
        "rollback_snapshot": {
            "product_id": 89416, "pt_versao": "28.4.1.1", "pt_versao_meta_id": 5940076,
            "variations": [
                {"id": 89417, "downloads": [downloads[0]]},
                {"id": 89418, "downloads": [downloads[1]]},
            ],
            "file_hash": CURRENT_SHA,
        },
    }


def observed_from(plan: dict) -> dict:
    return {item["key"]: item["expected"] for item in plan["preconditions"]}


class ExecutionPlanTests(unittest.TestCase):
    def test_plan_requires_ready_preview(self):
        with self.assertRaisesRegex(ValueError, "preview.ready=true"):
            build_execution_plan(prepared_job(), prepared_preview(ready=False))

    def test_plan_uses_effective_and_preserves_approved_version(self):
        job = prepared_job()
        plan = build_execution_plan(job, prepared_preview())
        self.assertEqual(plan["approved_source_version"], "28.5.6")
        self.assertEqual(plan["effective_source_version"], "28.5.7")
        self.assertEqual(plan["wordpress"]["pt_versao_future"], "28.5.7")
        self.assertEqual(job.approved_source_version, "28.5.6")
        self.assertEqual(job.state, JobState.PLAN_READY)

    def test_plan_accepts_canonical_local_staging_path_alias(self):
        preview = prepared_preview()
        expected_path = preview["new_zip"].pop("path")
        preview["new_zip"]["local_staging_path"] = expected_path
        plan = build_execution_plan(prepared_job(), preview)
        self.assertEqual(plan["new_zip"]["local_staging_path"], expected_path)

    def test_plan_recovers_persisted_job_staging_when_sha_matches(self):
        job = prepared_job()
        preview = prepared_preview()
        expected_path = preview["new_zip"].pop("path")
        job.local_staging_path = expected_path
        job.new_sha256 = NEW_SHA
        plan = build_execution_plan(job, preview)
        self.assertEqual(plan["new_zip"]["local_staging_path"], expected_path)

    def test_plan_rejects_persisted_staging_when_sha_does_not_match(self):
        job = prepared_job()
        preview = prepared_preview()
        job.local_staging_path = preview["new_zip"].pop("path")
        job.new_sha256 = "c" * 64
        with self.assertRaisesRegex(ValueError, "execute Preparar novamente"):
            build_execution_plan(job, preview)

    def test_each_generated_plan_has_a_new_nonempty_id(self):
        first = build_execution_plan(prepared_job(), prepared_preview())
        second = build_execution_plan(prepared_job(), prepared_preview())
        self.assertTrue(first["plan_id"])
        self.assertNotEqual(first["plan_id"], second["plan_id"])

    def test_plan_captures_both_hashes_original_version_and_download_state(self):
        plan = build_execution_plan(prepared_job(), prepared_preview())
        self.assertEqual(plan["current_zip"]["sha256"], CURRENT_SHA)
        self.assertEqual(plan["new_zip"]["sha256"], NEW_SHA)
        self.assertEqual(plan["new_zip"]["entries"], 42)
        self.assertEqual(plan["wordpress"]["pt_versao_current"], "28.4.1.1")
        self.assertEqual(plan["woocommerce"]["variation_ids"], [89417, 89418])
        self.assertEqual(plan["woocommerce"]["download_ids"], ["download-a", "download-b"])
        self.assertEqual(plan["woocommerce"]["current_file"], plan["woocommerce"]["future_file"])

    def test_plan_has_complete_preconditions(self):
        plan = build_execution_plan(prepared_job(), prepared_preview())
        self.assertEqual(
            {item["key"] for item in plan["preconditions"]},
            {"woo_product_id", "pt_versao", "remote_zip_sha256", "relationship",
             "local_zip_exists", "local_zip_sha256", "effective_source_version"},
        )
        self.assertTrue(evaluate_preconditions(plan, observed_from(plan))["ready"])

    def test_changed_remote_sha_blocks_future_execution(self):
        plan = build_execution_plan(prepared_job(), prepared_preview())
        observed = observed_from(plan)
        observed["remote_zip_sha256"] = "c" * 64
        result = evaluate_preconditions(plan, observed)
        self.assertFalse(result["ready"])
        self.assertEqual(result["message"], "BLOCKED — preparação ficou desatualizada")

    def test_changed_pt_versao_blocks_future_execution(self):
        plan = build_execution_plan(prepared_job(), prepared_preview())
        observed = observed_from(plan)
        observed["pt_versao"] = "28.4.2"
        self.assertFalse(evaluate_preconditions(plan, observed)["ready"])

    def test_rollback_is_complete(self):
        plan = build_execution_plan(prepared_job(), prepared_preview())
        rollback = plan["rollback"]
        self.assertEqual(rollback["original_zip"], plan["current_zip"]["remote_path"])
        self.assertEqual(rollback["original_sha256"], CURRENT_SHA)
        self.assertEqual(rollback["original_pt_versao"], "28.4.1.1")
        self.assertTrue(all(item["ok"] for item in rollback["checklist"]))
        self.assertTrue(rollback["original_variations"])
        self.assertTrue(rollback["original_downloads"])

    def test_builder_has_no_write_clients_or_execution_capability(self):
        parameters = set(inspect.signature(build_execution_plan).parameters)
        self.assertEqual(parameters, {"job", "preview", "logger"})
        plan = build_execution_plan(prepared_job(), prepared_preview())
        self.assertEqual(plan["execution_enabled"], settings.UPDATE_EXECUTION_ENABLED)
        self.assertNotIn("execute", plan)

    def test_logs_are_complete_and_secret_free(self):
        logs = []
        build_execution_plan(prepared_job(), prepared_preview(), logger=logs.append)
        self.assertEqual(logs, [
            "🧭 Gerando plano de execução", "🔎 Registrando estado atual",
            "📦 Registrando ZIP atual", "📥 Registrando ZIP preparado",
            "🛡 Gerando preconditions", "↩ Gerando plano de rollback",
            "✅ Plano de execução pronto",
        ])
        self.assertNotIn("password", " ".join(logs).lower())

    def test_ui_and_route_gate_individual_execution(self):
        js = Path("app/static/panel.js").read_text(encoding="utf-8")
        web = Path("app/web.py").read_text(encoding="utf-8")
        self.assertIn("Gerando plano de execução", js)
        self.assertIn("Plano pronto para homologação", js)
        self.assertIn('class="btn-danger update-execute"', js)
        self.assertNotIn("Executar selecionados", js)
        marker = 'if path == "/atualizacoes/executar":'
        route = web[web.index(marker):web.index(marker) + 1400]
        self.assertIn("UPDATE_EXECUTION_ENABLED", route)
        self.assertIn("UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", route)

    def test_all_write_flags_remain_false(self):
        self.assertIs(settings.WORDPRESS_WRITE_ENABLED, False)
        self.assertIs(settings.SSH_STORAGE_WRITE_ENABLED, False)
        self.assertIs(settings.SSH_HELPER_EXECUTION_ENABLED, False)


if __name__ == "__main__":
    unittest.main()
