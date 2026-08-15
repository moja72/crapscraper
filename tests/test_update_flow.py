from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.integrations.ultrapack_download import UltrapackDownloadError, UltrapackDownloader
from app.integrations.wordpress import WriteOperationDisabledError
from app.integrations.woocommerce_version import WooCommerceVersionWriter
from app.operations.models import JobState, OperationalJob
from app.operations.preparation import UpdatePreparationService
from app.operations.queue import materialize_queue
from app.configuration import missing_for

PRODUCT = {"id": 89416, "name": "AccessPress Anonymous Post Pro", "status": "publish",
           "date_modified_gmt": "2026-08-01", "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "3.2.6"}]}
DOWNLOAD = {"id": "download-a", "name": "AccessPress", "file": "/home/plugintema.com/downloads/AccessPress.zip"}
VARIATIONS = [{"id": item, "status": "publish", "virtual": True, "downloadable": True,
               "regular_price": "1", "sale_price": "", "attributes": [], "downloads": [DOWNLOAD]}
              for item in (89417, 89418)]

def job():
    return OperationalJob("cmp-1", 89416, PRODUCT["name"], "3.2.6", "3.2.7",
                          "https://ultrapack/item", "", "approve_update", "safe_auto", "update", job_id="JOB1")

class Woo:
    def __init__(self, product=None, variations=None): self.product, self.variations = product or PRODUCT, variations or VARIATIONS
    def get_product(self, _id): return self.product
    def list_variations(self, _id): return self.variations

class Storage:
    def validate_file(self, path):
        return SimpleNamespace(to_dict=lambda: {"path": path, "size": 10, "sha256": "a" * 64,
                                                "mode": "-rw-r--r--", "owner": "plugi2090", "group": "plugi2090"})

class Downloader:
    def __init__(self, found="3.2.7"): self.found = found
    def inspect_product(self, _url): return "https://ultrapack/item?f=redacted", self.found
    def download(self, _url, staging):
        return SimpleNamespace(to_dict=lambda: {"path": str(staging / "new.zip"), "file_name": "new.zip",
                                                "size": 20, "sha256": "b" * 64, "entries": 5}), self.found

class FakeResponse:
    def __init__(self, body=b"", status=200, content_type="application/octet-stream", text=None,
                 url="", headers=None):
        self.body, self.status_code = body, status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.url = url
        self.text = body.decode("utf-8", "replace") if text is None else text
    def iter_content(self, _size): yield self.body

class Session:
    def __init__(self, responses): self.responses, self.methods = list(responses), []
    def get(self, url, **_kwargs): self.methods.append(("GET", url)); return self.responses.pop(0)

class UpdateFlowTests(unittest.TestCase):
    def prepare_source(self, approved, found, *, relationship="safe_auto", logger=None):
        candidate = job()
        candidate.ultrapack_version = approved
        candidate.approved_source_version = approved
        candidate.relationship = relationship
        with tempfile.TemporaryDirectory() as tmp:
            return UpdatePreparationService(
                Woo(), Storage(), Downloader(found), staging_root=tmp,
                session_provider=lambda _job: object(), logger=logger,
            ).prepare(candidate), candidate

    def test_missing_ssh_is_detected_before_prepare_dependencies(self):
        configured = {
            "SCRAPER_WP_BASE_URL": "https://example.test",
            "SCRAPER_WC_CONSUMER_KEY": "key",
            "SCRAPER_WC_CONSUMER_SECRET": "secret",
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL": "user@example.test",
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD": "secret",
        }
        with mock.patch.dict(os.environ, configured, clear=True):
            missing = missing_for("prepare")
        self.assertEqual(missing, ("SCRAPER_SSH_HOST", "SCRAPER_SSH_PORT", "SCRAPER_SSH_USERNAME", "SCRAPER_SSH_PASSWORD"))

    def test_materializes_approved_job(self):
        decision = {"comparison_item_id": "cmp-1", "decision": "approve_update", "queue_type": "update", "site_id": "89416"}
        rows = [{**decision, "site_name": PRODUCT["name"], "site_version": "3.2.6", "source_version": "3.2.7",
                 "source_product_url": "https://ultrapack/item", "relationship_state": "safe_auto"}]
        result = materialize_queue(update_loader=lambda: [decision], addition_loader=lambda: [], comparison_rows=rows)
        self.assertEqual(result["update"][0].woo_product_id, 89416)
        self.assertEqual(result["update"][0].state, JobState.APPROVED)

    def test_preview_contains_real_fields_and_stays_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(Woo(), Storage(), Downloader(), staging_root=tmp,
                                               helper_probe=lambda: True).prepare(job())
        self.assertTrue(preview.ready)
        self.assertFalse(preview.execution_enabled)
        self.assertEqual(preview.variations, [89417, 89418])
        self.assertEqual(preview.rollback_snapshot["pt_versao_meta_id"], 5940076)
        self.assertEqual(preview.new_zip["sha256"], "b" * 64)

    def test_pt_versao_divergence_blocks_preview(self):
        changed = {**PRODUCT, "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "9.9"}]}
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(Woo(changed), Storage(), Downloader(), staging_root=tmp,
                                               helper_probe=lambda: True).prepare(job())
        self.assertFalse(preview.ready)
        self.assertEqual(preview.state, "blocked")

    def test_download_divergence_blocks_preview(self):
        broken = [{**VARIATIONS[0]}, {**VARIATIONS[1], "downloads": [{**DOWNLOAD, "file": "/home/plugintema.com/downloads/Other.zip"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(Woo(variations=broken), Storage(), Downloader(), staging_root=tmp,
                                               helper_probe=lambda: True).prepare(job())
        self.assertFalse(preview.ready)

    def test_zip_hash_and_corrupt_or_html_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "valid.zip"
            with zipfile.ZipFile(path, "w") as archive: archive.writestr("plugin/file.php", "ok")
            artifact = UltrapackDownloader.validate_zip(path)
            self.assertEqual(artifact.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            for name, content, message in (("html.zip", b"<!doctype html><html>erro", "HTML"),
                                           ("bad.zip", b"PK not really zip", "corrompido")):
                bad = Path(tmp) / name; bad.write_bytes(content)
                with self.assertRaisesRegex(UltrapackDownloadError, message): UltrapackDownloader.validate_zip(bad)

    def test_invalid_extension_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.bin"; path.write_bytes(b"")
            with self.assertRaises(UltrapackDownloadError): UltrapackDownloader.validate_zip(path)

    def test_html_response_rejected_without_non_get_methods(self):
        session = Session([FakeResponse(text='<a class="single-bt-download-a" data-f="file-7">baixar</a>', content_type="text/html"),
                           FakeResponse(b"<html>login</html>", content_type="text/html")])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(UltrapackDownloadError, "HTML"):
                UltrapackDownloader(session).download("https://ultrapack/item", tmp)
        self.assertEqual({method for method, _url in session.methods}, {"GET"})
        self.assertEqual(session.methods[1][1], "https://ultrapack/item?f=file-7")

    def test_discovers_only_real_data_f_button_and_encodes_identifier(self):
        html = ('<a href="/plugins/download-manager/">menu</a>'
                '<a class="button single-bt-download-a active" data-f="file id/+">Download</a>')
        found = UltrapackDownloader.discover_download_url("https://ultrapack/item?keep=1", html)
        self.assertEqual(found, "https://ultrapack/item?keep=1&f=file+id%2F%2B")

    def test_source_advance_is_allowed_only_for_safe_relationship(self):
        preview, advanced = self.prepare_source("3.2.6", "3.2.7")
        self.assertTrue(preview.ready)
        self.assertEqual(preview.versions["approved_source_version"], "3.2.6")
        self.assertEqual(preview.versions["effective_source_version"], "3.2.7")
        self.assertEqual(advanced.ultrapack_version, "3.2.6")
        self.assertEqual(advanced.approved_source_version, "3.2.6")
        self.assertEqual(advanced.effective_source_version, "3.2.7")
        detail = next(item.detail for item in preview.validations if item.key == "ultrapack")
        self.assertIn("Fonte avançou", detail)

    def test_equal_source_is_normal(self):
        preview, _candidate = self.prepare_source("3.2.6", "3.2.6")
        validation = next(item for item in preview.validations if item.key == "ultrapack")
        self.assertTrue(preview.ready)
        self.assertTrue(validation.ok)
        self.assertEqual(validation.level, "ok")
        self.assertEqual(preview.notices, [])

    def test_equal_source_without_rewritten_url_uses_approved_job_url(self):
        downloader = Downloader("3.2.7")
        downloader.inspect_product = lambda _url: ("", "3.2.7")
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(
                Woo(), Storage(), downloader, staging_root=tmp,
                session_provider=lambda _job: object(),
            ).prepare(job())
        validation = next(item for item in preview.validations if item.key == "ultrapack")
        self.assertTrue(validation.ok)
        self.assertTrue(preview.ready)

    def test_patch_minor_and_major_advances_are_informational(self):
        for found in ("3.2.7", "3.3.0", "4.0.0"):
            with self.subTest(found=found):
                preview, _candidate = self.prepare_source("3.2.6", found)
                validation = next(item for item in preview.validations if item.key == "ultrapack")
                self.assertTrue(preview.ready)
                self.assertTrue(validation.ok)
                self.assertEqual(validation.level, "info")
                self.assertEqual(preview.versions["effective_source_version"], found)
                self.assertTrue(preview.notices)

    def test_advanced_source_accepts_both_safe_relationships(self):
        for relationship in ("safe_auto", "manual_confirmed"):
            with self.subTest(relationship=relationship):
                preview, _candidate = self.prepare_source(
                    "28.5.6", "28.5.7", relationship=relationship
                )
                self.assertTrue(preview.ready)
                self.assertEqual(preview.state, "prepared")

    def test_advanced_source_with_unconfirmed_relationship_is_blocked(self):
        preview, _candidate = self.prepare_source(
            "3.2.6", "3.2.7", relationship="pending_review"
        )
        validation = next(item for item in preview.validations if item.key == "ultrapack")
        self.assertFalse(preview.ready)
        self.assertFalse(validation.ok)
        self.assertEqual(validation.level, "error")
        self.assertEqual(preview.state, "blocked")

    def test_advanced_source_logs_approved_found_and_effective_versions(self):
        logs = []
        preview, _candidate = self.prepare_source("28.5.6", "28.5.7", logger=logs.append)
        self.assertTrue(preview.ready)
        self.assertIn("🔎 Versão registrada na comparação: 28.5.6", logs)
        self.assertIn("🔎 Versão atual encontrada na fonte: 28.5.7", logs)
        self.assertIn("ℹ Fonte avançou desde a comparação; utilizando 28.5.7", logs)

    def test_betheme_preview_has_three_distinct_versions(self):
        betheme_product = {
            **PRODUCT,
            "name": "BeTheme",
            "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "28.4.1.1"}],
        }
        candidate = OperationalJob(
            "betheme", 89416, "BeTheme", "28.4.1.1", "28.5.6",
            "https://ultrapack/betheme", "", "approve_update",
            "manual_confirmed", "update", job_id="BETHEME",
        )
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(
                Woo(product=betheme_product), Storage(), Downloader("28.5.7"),
                staging_root=tmp, session_provider=lambda _job: object(),
            ).prepare(candidate)
        self.assertEqual(preview.versions["site_version"], "28.4.1.1")
        self.assertEqual(preview.versions["approved_source_version"], "28.5.6")
        self.assertEqual(preview.versions["effective_source_version"], "28.5.7")
        self.assertEqual(candidate.ultrapack_version, "28.5.6")
        self.assertEqual(candidate.approved_source_version, "28.5.6")
        self.assertEqual(candidate.effective_source_version, "28.5.7")
        self.assertTrue(preview.ready)

    def test_restart_legacy_job_without_version_fields_is_normalized(self):
        betheme_product = {
            **PRODUCT,
            "name": "BeTheme",
            "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "28.4.1.1"}],
        }
        candidate = OperationalJob(
            "betheme-restart", 89416, "BeTheme", "28.4.1.1", "28.5.6",
            "https://ultrapack/betheme", "", "approve_update",
            "manual_confirmed", "update", job_id="BETHEME-RESTART",
        )
        del candidate.approved_source_version
        del candidate.effective_source_version
        with tempfile.TemporaryDirectory() as tmp:
            preview = UpdatePreparationService(
                Woo(product=betheme_product), Storage(), Downloader("28.5.7"),
                staging_root=tmp, session_provider=lambda _job: object(),
            ).prepare(candidate)
        self.assertEqual(candidate.approved_source_version, "28.5.6")
        self.assertEqual(candidate.effective_source_version, "28.5.7")
        self.assertEqual(preview.versions["approved_source_version"], "28.5.6")
        self.assertEqual(preview.versions["effective_source_version"], "28.5.7")
        self.assertTrue(preview.ready)

    def test_new_job_keeps_original_approval_when_source_advances(self):
        preview, candidate = self.prepare_source("28.5.6", "28.5.7")
        self.assertTrue(preview.ready)
        self.assertEqual(candidate.approved_source_version, "28.5.6")
        self.assertEqual(candidate.effective_source_version, "28.5.7")

    def test_unexpected_prepare_error_restores_retryable_state_and_logs_failure(self):
        candidate = job()
        logs = []
        woo = Woo()
        woo.get_product = mock.Mock(side_effect=RuntimeError("temporary failure"))
        with tempfile.TemporaryDirectory() as tmp:
            service = UpdatePreparationService(
                woo, Storage(), Downloader(), staging_root=tmp, logger=logs.append,
            )
            with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                service.prepare(candidate)
        self.assertEqual(candidate.state, JobState.APPROVED)
        self.assertTrue(any("Preparando atualização" in entry for entry in logs))
        self.assertTrue(any("Falha na preparação: temporary failure" in entry for entry in logs))

    def test_older_or_invalid_source_blocks_before_download(self):
        for found in ("3.2.5", "not-a-version"):
            candidate = job()
            candidate.ultrapack_version = "3.2.6"
            candidate.approved_source_version = "3.2.6"
            downloader = Downloader(found)
            downloader.download = mock.Mock(side_effect=AssertionError("download nao deveria ocorrer"))
            with tempfile.TemporaryDirectory() as tmp:
                preview = UpdatePreparationService(
                    Woo(), Storage(), downloader, staging_root=tmp,
                    session_provider=lambda _job: object(),
                ).prepare(candidate)
            self.assertFalse(preview.ready)
            downloader.download.assert_not_called()

    def test_version_writer_prepares_rollback_but_never_patches_when_locked(self):
        calls = []
        writer = WooCommerceVersionWriter(Woo(), write_enabled=False, patch=lambda *args: calls.append(args))
        plan = writer.prepare(89416, "3.2.6", "3.2.7")
        self.assertEqual(plan.rollback_payload()["meta_data"][0], {"id": 5940076, "key": "pt_versao", "value": "3.2.6"})
        with self.assertRaises(WriteOperationDisabledError): writer.apply(plan)
        with self.assertRaises(WriteOperationDisabledError): writer.rollback(plan)
        self.assertEqual(calls, [])

    def test_ui_button_is_really_disabled(self):
        html = Path("app/static/panel.js").read_text(encoding="utf-8")
        self.assertIn('type="button" disabled aria-disabled="true"', html)
        self.assertIn("Execução real ainda bloqueada para homologação", html)

    def test_ui_renders_three_versions_and_advanced_source_as_info(self):
        html = Path("app/static/panel.js").read_text(encoding="utf-8")
        css = Path("app/static/panel.css").read_text(encoding="utf-8")
        for label in ("Versão PluginTema atual", "Versão na comparação", "Versão atual na fonte"):
            self.assertIn(label, html)
        self.assertIn('item?.level === "info" ? "is-info"', html)
        self.assertIn('class="update-source-notice" role="status"', html)
        self.assertIn(".update-check.is-info", css)
        self.assertNotIn(".update-check.is-info{border-color:var(--danger)", css)

    def test_execute_endpoint_is_individual_and_guarded(self):
        source = Path("app/web.py").read_text(encoding="utf-8")
        marker = 'if path == "/atualizacoes/executar":'
        route = source[source.index(marker):source.index(marker) + 1500]
        self.assertIn("UPDATE_EXECUTION_ENABLED", route)
        self.assertIn("confirmation", route)
        self.assertIn("plan_id", route)

    def test_prepare_route_checks_configuration_before_service_or_download(self):
        source = Path("app/web.py").read_text(encoding="utf-8")
        marker = 'if path == "/atualizacoes/preparar":'
        route = source[source.index(marker):source.index(marker) + 2200]
        self.assertLess(route.index('missing_for("prepare")'), route.index("_build_update_preparation_service"))
        self.assertIn("Nenhum download foi iniciado", route)

    def test_executor_service_never_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = UpdatePreparationService(Woo(), Storage(), Downloader(), staging_root=tmp)
            with self.assertRaises(WriteOperationDisabledError): service.execute(job())

if __name__ == "__main__": unittest.main()
