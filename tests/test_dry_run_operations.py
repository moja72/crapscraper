from __future__ import annotations

import unittest
from urllib.error import URLError

from app.integrations.wordpress import (
    IntegrationError,
    ReadOnlyHttpClient,
    WriteOperationDisabledError,
)
from app.integrations.woocommerce import pt_versao, variation_downloads
from app.integrations.ssh_storage import RemoteFileInfo
from app.operations.executor import DryRunExecutor
from app.operations.models import JobState, OperationalJob
from app.operations.queue import materialize_queue
from app.operations.rollback import build_snapshot


PRODUCT = {
    "id": 89416,
    "name": "AccessPress Anonymous Post Pro",
    "status": "publish",
    "date_modified_gmt": "2026-08-01T00:00:00",
    "meta_data": [{"id": 5940076, "key": "pt_versao", "value": "3.2.6"}],
}
VARIATIONS = [
    {
        "id": 89417,
        "status": "publish",
        "regular_price": "59.9",
        "sale_price": "39.8",
        "virtual": True,
        "downloadable": True,
        "attributes": [{"id": 4, "option": "1 Ano"}],
        "downloads": [{
            "id": "uuid-one-year",
            "name": "AccessPress Anonymous Post Pro",
            "file": "/home/plugintema.com/downloads/AccessPressAnonymousPostPro.zip",
        }],
    },
    {
        "id": 89418,
        "status": "publish",
        "regular_price": "59.9",
        "sale_price": "39.8",
        "virtual": True,
        "downloadable": True,
        "attributes": [{"id": 4, "option": "Vitalicio"}],
        "downloads": [{
            "id": "uuid-lifetime",
            "name": "AccessPress Anonymous Post Pro",
            "file": "/home/plugintema.com/downloads/AccessPressAnonymousPostPro.zip",
        }],
    },
]


class FakeWoo:
    def get_product(self, product_id: int):
        self.last_product_id = product_id
        return PRODUCT

    def list_variations(self, product_id: int):
        self.last_variation_parent = product_id
        return VARIATIONS


class FakeStorage:
    def validate_file(self, path: str):
        return RemoteFileInfo(
            path=path, resolved_path=path, size=12345, mtime=1770000000,
            mode="-rw-r--r--", uid=1000, gid=1000, owner="plugin",
            group="nobody", sha256="a" * 64,
        )


def update_job() -> OperationalJob:
    return OperationalJob(
        comparison_item_id="comparison-accesspress",
        woo_product_id=89416,
        name="AccessPress Anonymous Post Pro",
        plugintema_version="3.2.6",
        ultrapack_version="3.2.7",
        ultrapack_url="https://example.invalid/item/accesspress",
        official_url="https://example.invalid/official/accesspress",
        decision="approve_update",
        relationship="safe_auto",
        queue_type="update",
    )


class ReadOnlyClientTests(unittest.TestCase):
    def test_error_sanitizes_credentials(self) -> None:
        username = "private-user"
        password = "private-password"

        def broken(_request, _timeout):
            raise URLError(f"failure {username} {password}")

        client = ReadOnlyHttpClient(
            "https://example.invalid", username, password,
            retries=0, transport=broken,
        )
        with self.assertRaises(IntegrationError) as captured:
            client.get("/read")
        message = str(captured.exception)
        self.assertNotIn(username, message)
        self.assertNotIn(password, message)
        self.assertIn("[REDACTED]", message)

    def test_all_write_paths_are_blocked(self) -> None:
        client = ReadOnlyHttpClient("https://example.invalid", "u", "p")
        with self.assertRaises(WriteOperationDisabledError):
            client._request("POST", "/anything")
        with self.assertRaises(WriteOperationDisabledError):
            client.write()


class ParsingTests(unittest.TestCase):
    def test_parses_pt_versao_and_downloads(self) -> None:
        self.assertEqual(pt_versao(PRODUCT), "3.2.6")
        parsed = variation_downloads(VARIATIONS[0])
        self.assertEqual(parsed[0]["id"], "uuid-one-year")
        self.assertEqual(parsed[0]["file"], VARIATIONS[0]["downloads"][0]["file"])


class QueueTests(unittest.TestCase):
    def test_materializes_existing_decision_types_without_renaming(self) -> None:
        update = {
            "comparison_item_id": "update-1", "decision": "approve_update",
            "queue_type": "update", "site_id": "89416", "site_name": "AccessPress",
        }
        addition = {
            "comparison_item_id": "new-1", "decision": "approve_new_product",
            "queue_type": "new_product", "source_name": "New Theme",
        }
        rows = [
            {"comparison_item_id": "update-1", "site_version": "1", "source_version": "2"},
            {"comparison_item_id": "new-1", "source_version": "1.0", "source_product_url": "https://source"},
        ]
        queues = materialize_queue(
            update_loader=lambda: [update], addition_loader=lambda: [addition],
            comparison_rows=rows,
        )
        self.assertEqual(queues["update"][0].queue_type, "update")
        self.assertEqual(queues["new_product"][0].decision, "approve_new_product")
        self.assertEqual(queues["new_product"][0].woo_product_id, 0)


class DryRunTests(unittest.TestCase):
    def test_update_plan_preserves_download_identifiers_and_paths(self) -> None:
        job = update_job()
        plan = DryRunExecutor(FakeWoo(), storage=FakeStorage()).plan_update(job)
        self.assertEqual(job.state, JobState.DRY_RUN_READY)
        self.assertTrue(plan.write_blocked)
        self.assertEqual(plan.variation_ids, [89417, 89418])
        self.assertEqual(
            {item["id"] for item in plan.download_entries},
            {"uuid-one-year", "uuid-lifetime"},
        )
        self.assertEqual(len({item["file"] for item in plan.download_entries}), 1)
        self.assertEqual(plan.physical_validation["size"], 12345)
        self.assertEqual(plan.physical_validation["sha256"], "a" * 64)

    def test_executor_requires_both_safety_locks(self) -> None:
        with self.assertRaises(WriteOperationDisabledError):
            DryRunExecutor(FakeWoo(), dry_run=False, storage=FakeStorage()).plan_update(update_job())
        with self.assertRaises(WriteOperationDisabledError):
            DryRunExecutor(FakeWoo(), write_enabled=True, storage=FakeStorage()).plan_update(update_job())
        with self.assertRaises(WriteOperationDisabledError):
            DryRunExecutor(FakeWoo()).execute(update_job())

    def test_update_is_blocked_without_physical_storage_validation(self) -> None:
        job = update_job()
        with self.assertRaisesRegex(ValueError, "Armazenamento SSH read-only"):
            DryRunExecutor(FakeWoo()).plan_update(job)
        self.assertEqual(job.state, JobState.BLOCKED)

    def test_new_product_preview_is_always_draft_and_has_undefined_prices(self) -> None:
        job = OperationalJob(
            comparison_item_id="new-1", woo_product_id=0, name="New Theme",
            plugintema_version="", ultrapack_version="1.0",
            ultrapack_url="https://example.invalid/new",
            official_url="https://example.invalid/official",
            decision="approve_new_product", relationship="confirmed_new",
            queue_type="new_product",
        )
        preview = DryRunExecutor(FakeWoo()).plan_new_product(job)
        payload = preview.payload_preview
        self.assertEqual(payload["product"]["status"], "draft")
        self.assertEqual(len(payload["variations"]), 2)
        self.assertTrue(all(item["status"] == "draft" for item in payload["variations"]))
        self.assertTrue(all(item["regular_price"] == "NAO DEFINIDO" for item in payload["variations"]))


class RollbackTests(unittest.TestCase):
    def test_snapshot_captures_meta_variations_and_download_uuids(self) -> None:
        snapshot = build_snapshot(PRODUCT, VARIATIONS, captured_at="2026-08-12T00:00:00Z")
        self.assertEqual(snapshot.pt_versao, "3.2.6")
        self.assertEqual(snapshot.pt_versao_meta_id, 5940076)
        self.assertEqual(snapshot.variations[0].downloads[0].id, "uuid-one-year")
        self.assertIsNone(snapshot.file_hash)


if __name__ == "__main__":
    unittest.main()
