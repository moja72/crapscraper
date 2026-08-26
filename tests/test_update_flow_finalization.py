from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.integrations.download_validation import InvalidDownloadPayload, write_validated_zip_response
from app.operations.models import JobState, OperationalJob
import app.operations.runtime as runtime
import app.operational_simple_flow_policy as simple_flow
import app.update_flow_finalization_policy as finalization
import app.update_recoverability_policy as recoverability
from app.update_error_model import normalize_update_error


def make_job(job_id: str = "FLOW-1") -> OperationalJob:
    job = OperationalJob(
        "comparison-flow", 92473, "GeoDirectory Custom Post Types", "2.3.18", "2.3.19",
        "https://www.ultrapackv2.com/item/geodirectory/", "", "approve_update",
        "safe_auto", "update", job_id=job_id,
    )
    job.approved_source_version = "2.3.18"
    job.effective_source_version = "2.3.19"
    return job


class FakeResponse:
    def __init__(self, body: bytes, *, url: str, content_type: str = "text/html", status: int = 200):
        self._body = body
        self.url = url
        self.status_code = status
        self.history = []
        self.headers = {"Content-Type": content_type}

    def iter_content(self, _size: int):
        yield self._body


class UpdateFlowFinalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = dict(runtime._JOBS)
        self.previews = dict(runtime._PREVIEWS)
        self.plans = dict(runtime._PLANS)
        runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()

    def tearDown(self) -> None:
        runtime._JOBS.clear(); runtime._JOBS.update(self.jobs)
        runtime._PREVIEWS.clear(); runtime._PREVIEWS.update(self.previews)
        runtime._PLANS.clear(); runtime._PLANS.update(self.plans)

    def test_scenario_a_individual_success_uses_canonical_executor(self) -> None:
        job = make_job("SUCCESS")
        job.state = JobState.PLAN_READY
        runtime._JOBS[job.job_id] = job
        preview = {"ready": True}
        plan = {"ready": True, "job_id": job.job_id, "woo_product_id": job.woo_product_id,
                "new_zip": {"local_staging_path": __file__}}
        runtime._PREVIEWS[job.job_id] = preview
        runtime._PLANS[job.job_id] = plan

        class Executor:
            def execute(self, current, _plan, _confirmation):
                current.set_state(JobState.COMPLETED, "ok")

        with patch.object(runtime, "is_execution_eligible", return_value=True), \
             patch.object(runtime, "persist_job", return_value=None), \
             patch.object(finalization.web, "_build_controlled_update_executor", return_value=Executor()):
            result = finalization.execute_update_job(job.job_id, manager=None)

        self.assertTrue(result["ok"])
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertEqual(job.attempts, 1)

    def test_scenario_b_html_is_never_saved_as_zip_and_is_diagnosed(self) -> None:
        body = b"<!doctype html><html><body><form><input type='password'>Sign in</form></body></html>"
        response = FakeResponse(body, url="https://www.ultrapackv2.com/login")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "invalid.zip"
            with self.assertRaises(InvalidDownloadPayload) as raised:
                write_validated_zip_response(
                    response,
                    requested_url="https://www.ultrapackv2.com/item/x/?f=temporary",
                    target=target,
                    max_bytes=1024 * 1024,
                )
            self.assertFalse(target.exists())
        diagnostic = raised.exception.diagnostic
        self.assertEqual(diagnostic["response_kind"], "html")
        self.assertIn("login", diagnostic["probable_cause"].lower())
        self.assertEqual(diagnostic["status"], 200)
        self.assertIn("Content-Type", str(raised.exception))

    def test_failed_final_download_is_not_repeated_by_recovery(self) -> None:
        service = SimpleNamespace(
            downloader=SimpleNamespace(request_trace=[{"stage": "final_download"}]),
            logger=Mock(),
        )
        with patch.object(finalization, "_BASE_RECOVERY_REUSE", Mock()) as fallback:
            with self.assertRaisesRegex(RuntimeError, "não será repetida"):
                finalization._recovery_reuse_without_duplicate_network(
                    service,
                    make_job("NO-LOOP"),
                    target_version="2.3.19",
                    previous_path="",
                    previous_sha="",
                    previous_version="",
                )
            fallback.assert_not_called()

    def test_scenario_c_retry_archives_error_and_resets_only_current_state(self) -> None:
        job = make_job("RETRY")
        job.state = JobState.BLOCKED
        job.execution_error = "Resposta HTML recebida no lugar do ZIP"
        job.execution_logs = ["erro anterior"]
        runtime._JOBS[job.job_id] = job
        runtime._PREVIEWS[job.job_id] = {"ready": False}
        runtime._PLANS[job.job_id] = {"ready": False}
        with patch.object(runtime, "_persist", return_value=None):
            retried = recoverability._reset_for_retry(job.job_id, manager=None)
        self.assertEqual(retried.state, JobState.APPROVED)
        self.assertEqual(retried.execution_error, "")
        self.assertEqual(retried.execution_logs, [])
        self.assertNotIn(job.job_id, runtime._PREVIEWS)
        self.assertNotIn(job.job_id, runtime._PLANS)
        self.assertTrue(retried.execution_history)
        self.assertIn("HTML", retried.execution_history[-1]["error"])

    def test_scenario_d_batch_continues_after_one_product_failure(self) -> None:
        ids = ["A", "B", "C"]
        simple_flow._BATCHES["update"] = simple_flow._empty_batch("update")
        simple_flow._BATCHES["update"].update(running=True, total=3)
        outcomes = [
            {"job_id": "A", "ok": True, "status": "completed", "message": "ok"},
            RuntimeError("falha B"),
            {"job_id": "C", "ok": True, "status": "completed", "message": "ok"},
        ]
        with patch.object(finalization, "execute_update_job", side_effect=outcomes), \
             patch.object(runtime, "get_job", side_effect=KeyError):
            finalization._run_batch_canonical("update", ids, manager=None)
        batch = simple_flow._batch_public("update")
        self.assertTrue(batch["done"])
        self.assertEqual(batch["processed"], 3)
        self.assertEqual(batch["success"], 2)
        self.assertEqual(batch["errors"], 1)
        self.assertIn("2 concluído(s)", batch["message"])
        self.assertIn("1 com erro", batch["message"])

    def test_global_auth_failure_pauses_remaining_batch_without_marking_them_failed(self) -> None:
        ids = ["A", "B", "C"]
        simple_flow._BATCHES["update"] = simple_flow._empty_batch("update")
        simple_flow._BATCHES["update"].update(running=True, total=3)
        auth_job = make_job("A")
        auth_job.state = JobState.BLOCKED
        auth_job.execution_error = "Sessão expirada; login necessário"
        runtime._JOBS["A"] = auth_job
        with patch.object(finalization, "execute_update_job", side_effect=RuntimeError(auth_job.execution_error)):
            finalization._run_batch_canonical("update", ids, manager=None)
        batch = simple_flow._batch_public("update")
        self.assertFalse(batch["running"])
        self.assertFalse(batch["done"])
        self.assertTrue(batch["global_block"])
        self.assertEqual(batch["processed"], 1)
        self.assertEqual(batch["errors"], 1)

    def test_scenario_f_card_and_history_share_same_normalized_error(self) -> None:
        job = make_job("PARITY")
        job.state = JobState.BLOCKED
        job.execution_error = "Download inválido: servidor não entregou um ZIP utilizável."
        preview = {
            "versions": {"approved_source_version": "2.3.18", "effective_source_version": "2.3.19"},
            "new_zip": {"error": job.execution_error, "download_diagnostic": {
                "requested_url": "https://source.test/download?token=%5Bredacted%5D",
                "final_url": "https://source.test/login",
                "status": 200,
                "content_type": "text/html",
                "probable_cause": "sessão expirada / página de login",
            }},
        }
        runtime._JOBS[job.job_id] = job
        runtime._PREVIEWS[job.job_id] = preview
        canonical = normalize_update_error(job, preview, {})

        old_public = finalization._BASE_JOB_PUBLIC
        old_history = finalization._BASE_HISTORY_ROWS
        try:
            finalization._BASE_JOB_PUBLIC = lambda current: {"job_id": current.job_id, "execution_error": current.execution_error}
            public = finalization._public_job(job)
            finalization._BASE_HISTORY_ROWS = lambda: [{"job_id": job.job_id, "error": "old", "result": "old"}]
            history = finalization._history_rows()[0]
        finally:
            finalization._BASE_JOB_PUBLIC = old_public
            finalization._BASE_HISTORY_ROWS = old_history

        self.assertEqual(public["execution_error"], canonical["display_text"])
        self.assertEqual(history["error"], canonical["display_text"])
        self.assertEqual(public["normalized_error"], history["normalized_error"])


class UpdateTechnicalLogContractTests(unittest.TestCase):
    def test_scenario_e_only_technical_script_controls_native_details_toggle(self) -> None:
        technical = Path("app/static/update_technical_log_fix.js").read_text(encoding="utf-8")
        retry = Path("app/static/update_retry_recovery_v2.js").read_text(encoding="utf-8")
        self.assertIn('addEventListener("toggle"', technical)
        self.assertNotIn('summary.addEventListener("click"', technical)
        self.assertNotIn('summary.addEventListener("keydown"', technical)
        self.assertNotIn("details.open = !details.open", technical)
        self.assertNotIn("TECHNICAL_SELECTOR", retry)
        self.assertNotIn("details.open", retry)

    def test_waiting_summary_card_is_removed_but_prepared_is_kept(self) -> None:
        source = Path("app/static/update_flow_final.js").read_text(encoding="utf-8")
        self.assertIn('labelOf(card) === "Preparados"', source)
        self.assertIn('labelOf(card) === "Aguardando"', source)
        self.assertIn("waiting.remove()", source)


if __name__ == "__main__":
    unittest.main()
