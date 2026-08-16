from __future__ import annotations

import hashlib
import hmac
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.wordpress_manual_update import (
    create_manual_job, select_manual_candidate, verify_signed_request,
)


class Woo:
    def get_product(self, product_id):
        return {
            "id": product_id, "name": "Produto manual",
            "categories": [{"name": "Plugins"}],
            "meta_data": [{"key": "pt_versao", "value": "1.0.0"}],
        }


def decision(source_url, version, relationship="manual_confirmed"):
    return {
        "comparison_item_id": source_url, "woo_product_id": 42,
        "site_id": 42, "site_name": "Produto manual", "source_version": version,
        "source_product_url": source_url, "source_official_url": "https://official.invalid",
        "relationship_state": relationship, "queue_type": "update",
    }


class WordPressManualUpdateTests(unittest.TestCase):
    def test_plugintheme_is_prioritized_and_ultrapack_is_fallback(self):
        rows = [
            decision("https://ultrapackv2.com/item", "3.0.0"),
            decision("https://plugintheme.net/item", "2.0.0"),
        ]
        selected = select_manual_candidate(42, "1.0.0", rows)
        self.assertEqual(selected["manual_source_name"], "PluginTheme")
        fallback = select_manual_candidate(42, "2.0.0", rows)
        self.assertEqual(fallback["manual_source_name"], "UltraPackV2")

    def test_unsafe_or_old_relationship_is_not_selected(self):
        rows = [decision("https://plugintheme.net/item", "2.0.0", "pending_review")]
        self.assertIsNone(select_manual_candidate(42, "1.0.0", rows))

    def test_hmac_rejects_replay(self):
        secret = "x" * 32
        now = int(time.time())
        nonce = "nonce-test-replay"
        message = f"{now}\n{nonce}\nPOST\n/wordpress/manual-update\n42"
        headers = {
            "X-CrapScraper-Timestamp": str(now), "X-CrapScraper-Nonce": nonce,
            "X-CrapScraper-Signature": hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest(),
        }
        verify_signed_request(headers, "POST", "/wordpress/manual-update", "42", now=now, secret=secret)
        with self.assertRaises(PermissionError):
            verify_signed_request(headers, "POST", "/wordpress/manual-update", "42", now=now, secret=secret)

    def test_job_is_registered_in_manual_queue_with_audit_fields(self):
        row = decision("https://plugintheme.net/item", "2.0.0")
        with patch("app.wordpress_manual_update.get_active_manual_job", return_value=None), \
             patch("app.wordpress_manual_update.list_decisions", return_value=[row]), \
             patch("app.wordpress_manual_update.register_manual_job") as register:
            job, response = create_manual_job(Woo(), 42, initiated_by="root (#1)")
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(job.source_name, "PluginTheme")
        self.assertEqual(job.initiated_by, "root (#1)")
        self.assertTrue(job.manual_requested_at)
        register.assert_called_once_with(job)

    def test_active_manual_job_is_reused(self):
        existing = type("Job", (), {"job_id": "same", "source_name": "PluginTheme",
                    "plugintema_version": "1.0", "effective_source_version": "2.0",
                    "approved_source_version": "2.0"})()
        with patch("app.wordpress_manual_update.get_active_manual_job", return_value=existing):
            job, response = create_manual_job(Woo(), 42, initiated_by="root")
        self.assertIs(job, existing)
        self.assertTrue(response["reused"])

    def test_wordpress_plugin_has_server_side_super_admin_and_ui_states(self):
        root = Path(__file__).resolve().parents[1]
        php = (root / "deploy/wordpress/crapscraper-manual-update/crapscraper-manual-update.php").read_text(encoding="utf-8")
        js = (root / "deploy/wordpress/crapscraper-manual-update/manual-update.js").read_text(encoding="utf-8")
        web = (root / "app/web.py").read_text(encoding="utf-8")
        self.assertIn("is_super_admin(get_current_user_id())", php)
        self.assertIn("check_ajax_referer", php)
        self.assertIn("hash_hmac('sha256'", php)
        for state in ("loading", "success", "error", "empty"):
            self.assertIn(state, js)
        self.assertIn('/wordpress/manual-update/status', web)
        self.assertIn('verify_signed_request', web)
        runtime = (root / "app/operations/runtime.py").read_text(encoding="utf-8")
        for field in ("source", "previous_version", "new_version", "requested_at", "result"):
            self.assertIn(f'"{field}"', runtime)


if __name__ == "__main__":
    unittest.main()
