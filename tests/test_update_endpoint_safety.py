from __future__ import annotations

import json
import threading
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from pathlib import Path

from app.app import ScraperRunManager
from app.web import make_handler
from app.operations import runtime
from app.operations.models import JobState, OperationalJob
from app import settings


class UpdateEndpointSafetyTests(unittest.TestCase):
    def test_endpoint_revalidates_astra_whitelist_before_builder(self):
        manager = ScraperRunManager()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "UPDATE_RUNTIME_PATH", Path(directory) / "runtime.json"
        ):
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            job = OperationalJob("astra", 90109, "Astra", "4.13.1", "4.13.9", "u", "",
                                 "approve_update", "safe_auto", "update", job_id="ASTRA-ENDPOINT")
            job.state = JobState.PLAN_READY
            local_zip = Path(directory) / "astra.zip"; local_zip.write_bytes(b"prepared")
            runtime.persist_job(job); runtime.save_preview(job.job_id, {"ready": True})
            runtime.save_plan(job.job_id, {"plan_id": "ASTRA-PLAN", "job_id": job.job_id,
                "woo_product_id": 90109, "ready": True,
                "new_zip": {"local_staging_path": str(local_zip)},
                "backup": {"path": "/downloads/astra.bak"}})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            request = Request(f"http://127.0.0.1:{server.server_port}/atualizacoes/executar",
                data=json.dumps({"job_id": job.job_id, "plan_id": "ASTRA-PLAN",
                                 "confirmation": "EXECUTAR 90109"}).encode(), method="POST",
                headers={"Content-Type": "application/json"})
            try:
                with patch("app.web.settings.UPDATE_EXECUTION_ENABLED", True), patch(
                    "app.web.settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", frozenset({94567})
                ), patch("app.web._build_controlled_update_executor") as builder:
                    with self.assertRaises(HTTPError) as caught: urlopen(request, timeout=5)
                    self.assertEqual(caught.exception.code, 403)
                    builder.assert_not_called()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_disabled_endpoint_returns_403_before_write_capable_builder(self):
        manager = ScraperRunManager()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = json.dumps({"job_id": "VALID", "plan_id": "VALID", "confirmation": "EXECUTAR 94567"}).encode()
        request = Request(f"http://127.0.0.1:{server.server_port}/atualizacoes/executar",
                          data=payload, method="POST", headers={"Content-Type": "application/json"})
        try:
            with patch("app.web.settings.UPDATE_EXECUTION_ENABLED", False), patch(
                "app.web._build_controlled_update_executor"
            ) as builder:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 403)
                body = json.loads(caught.exception.read())
                self.assertIn("bloqueada", body["message"].lower())
                builder.assert_not_called()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_two_execution_requests_start_only_one_worker(self):
        manager = ScraperRunManager(); release = threading.Event(); started = threading.Event()
        class Executor:
            def execute(self, job, _plan, _confirmation):
                started.set(); release.wait(5); job.set_state(JobState.COMPLETED)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "UPDATE_RUNTIME_PATH", Path(directory) / "runtime.json"
        ), patch("app.web.settings.UPDATE_EXECUTION_ENABLED", True), patch(
            "app.web.settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", frozenset({94567})
        ), patch("app.web._build_controlled_update_executor", return_value=Executor()) as builder:
            runtime._JOBS.clear(); runtime._PREVIEWS.clear(); runtime._PLANS.clear()
            job = OperationalJob("c", 94567, "BeTheme", "1", "2", "u", "", "approve_update",
                                 "manual_confirmed", "update", job_id="CONCURRENT")
            job.state = JobState.PLAN_READY
            local_zip = Path(directory) / "betheme.zip"
            local_zip.write_bytes(b"prepared")
            runtime.persist_job(job); runtime.save_preview(job.job_id, {"ready": True})
            runtime.save_plan(job.job_id, {"plan_id": "P", "job_id": job.job_id,
                                           "woo_product_id": 94567, "ready": True,
                                           "new_zip": {"local_staging_path": str(local_zip)},
                                           "backup": {"path": "/downloads/betheme.bak"}})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            body = json.dumps({"job_id": job.job_id, "plan_id": "P",
                               "confirmation": "EXECUTAR 94567"}).encode()
            def call():
                request = Request(f"http://127.0.0.1:{server.server_port}/atualizacoes/executar",
                                  data=body, method="POST", headers={"Content-Type": "application/json"})
                try: return urlopen(request, timeout=5).status
                except HTTPError as error: return error.code
            try:
                first = call(); self.assertEqual(first, 202); self.assertTrue(started.wait(2))
                second = call(); self.assertIn(second, {400, 409})
                self.assertEqual(builder.call_count, 1)
            finally:
                release.set(); server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__": unittest.main()
