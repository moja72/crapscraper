from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

from app.wordpress_manual_update import (
    WordPressManualQueueClient, create_manual_job, evaluate_manual_candidates, select_manual_candidate,
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
    def test_highest_new_version_wins_and_source_priority_only_breaks_ties(self):
        rows = [
            decision("https://ultrapackv2.com/item", "3.0.0"),
            decision("https://plugintheme.net/item", "2.0.0"),
        ]
        selected = select_manual_candidate(42, "1.0.0", rows)
        self.assertEqual(selected["manual_source_name"], "UltraPackV2")
        tied = [decision("https://ultrapackv2.com/item", "3.0.0"),
                decision("https://plugintheme.net/item", "3.0.0")]
        self.assertEqual(select_manual_candidate(42, "1.0.0", tied)["manual_source_name"], "PluginTheme")

    def test_requested_version_scenarios_choose_ultrapack(self):
        first = [decision("https://plugintheme.net/item", "4.0.4"),
                 decision("https://ultrapackv2.com/item", "4.1.0")]
        second = [decision("https://plugintheme.net/item", "4.1.0"),
                  decision("https://ultrapackv2.com/item", "4.2.0")]
        self.assertEqual(select_manual_candidate(42, "4.0.4", first)["source_version"], "4.1.0")
        self.assertEqual(select_manual_candidate(42, "4.0.4", second)["source_version"], "4.2.0")

    def test_empty_missing_equal_and_unsafe_are_distinct(self):
        self.assertEqual(evaluate_manual_candidates(42, "4.0.4", [])["status"], "no_match")
        equal = [decision("https://plugintheme.net/item", "4.0.4")]
        self.assertEqual(evaluate_manual_candidates(42, "4.0.4", equal)["status"], "up_to_date")
        missing = [decision("https://plugintheme.net/item", "")]
        self.assertEqual(evaluate_manual_candidates(42, "4.0.4", missing)["status"], "source_version_missing")
        unsafe = [decision("https://ultrapackv2.com/item", "4.2.0", "pending_review")]
        self.assertEqual(evaluate_manual_candidates(42, "4.0.4", unsafe)["status"], "relationship_required")

    def test_unsafe_or_old_relationship_is_not_selected(self):
        rows = [decision("https://plugintheme.net/item", "2.0.0", "pending_review")]
        self.assertIsNone(select_manual_candidate(42, "1.0.0", rows))

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
        self.assertIn("is_super_admin(get_current_user_id())", php)
        self.assertIn("check_ajax_referer", php)
        self.assertIn("hash_hmac('sha256'", php)
        self.assertIn("register_rest_route('crapscraper/v1'", php)
        self.assertIn("crapscraper_manual_updates", php)
        self.assertNotIn("CRAPSCRAPER_MANUAL_API_URL", php)
        for state in ("loading", "success", "error", "empty"):
            self.assertIn(state, js)
        for header in ("Cache-Control", "CDN-Cache-Control", "litespeed_control_set_nocache"):
            self.assertIn(header, php)
        for frontend in ("wp_enqueue_scripts", "wp_footer", "frontend_product_id",
                         "render_component($product_id, 'frontend')", "cs-frontend-panel"):
            self.assertIn(frontend, php)
        self.assertIn("data-cs-stage", php)
        self.assertIn("data-cs-source", php)
        self.assertIn("data-cs-version", php)
        self.assertIn("Ainda não definida", js)
        css = (root / "deploy/wordpress/crapscraper-manual-update/manual-update.css").read_text(encoding="utf-8")
        self.assertIn("position:fixed", css)
        self.assertIn("top:20px", css)
        self.assertIn("right:20px", css)
        self.assertIn("prefers-reduced-motion", css)
        for interaction in ("data-cs-drag-handle", "data-cs-minimize", "Arraste para mover"):
            self.assertIn(interaction, php)
        for behavior in ("localStorage", "setPointerCapture", "is-minimized", "ArrowLeft", "event.key === 'Home'"):
            self.assertIn(behavior, js)
        self.assertIn(".cs-frontend-panel.is-minimized", css)
        self.assertIn("touch-action:none", css)
        runtime = (root / "app/operations/runtime.py").read_text(encoding="utf-8")
        for field in ("source", "previous_version", "new_version", "requested_at", "result"):
            self.assertIn(f'"{field}"', runtime)

    def test_local_client_polls_wordpress_over_https_with_hmac(self):
        response = type("Response", (), {
            "__enter__": lambda self: self, "__exit__": lambda self, *args: None,
            "read": lambda self: json.dumps({"ok": True, "requests": [{"request_id": "r1"}]}).encode(),
        })()
        client = WordPressManualQueueClient("https://plugintema.com", "s" * 32)
        with patch("app.wordpress_manual_update.urlopen", return_value=response) as request:
            rows = client.pending()
        self.assertEqual(rows[0]["request_id"], "r1")
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, "https://plugintema.com/wp-json/crapscraper/v1/manual-updates/pending")
        self.assertTrue(sent.headers.get("X-crapscraper-signature"))

    def test_store_panel_uses_real_worker_monitor_and_sanitized_rest_errors(self):
        root = Path(__file__).resolve().parents[1]
        web = (root / "app/web.py").read_text(encoding="utf-8")
        panel = (root / "app/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("Atualizações solicitadas pelo WordPress", web)
        self.assertIn("manual_monitor_snapshot", web)
        self.assertIn("UpdateLogger.sanitize(error)", web)
        self.assertNotIn("def _start_wordpress_manual_worker(manager: Any):\n", web.split("def _start_wordpress_manual_worker_legacy", 1)[0])
        self.assertIn("refreshWordPressManualMonitor", panel)
        self.assertIn("Erro de conexão/autenticação", panel)


if __name__ == "__main__":
    unittest.main()
