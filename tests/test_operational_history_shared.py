from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.operational_history_shared_policy as shared


NORMALIZED_ITEM = {
    "id": "job-1",
    "operation_type": "addition",
    "job_id": "job-1",
    "name": "Produto",
    "woo_product_id": 42,
    "attempt_no": 1,
    "state": "completed",
    "state_label": "Concluído",
    "bucket": "completed",
    "result": "OK",
    "origin": "UltraPack",
    "source_url": "https://source.invalid/item",
    "official_url": "https://official.invalid/item",
    "developer": "Dev",
    "category": "Categoria",
    "product_type": "Plugin",
    "previous_version": "",
    "new_version": "2.0",
    "started_at": "2026-08-01T10:00:00+00:00",
    "finished_at": "2026-08-01T10:01:00+00:00",
    "date": "2026-08-01T10:01:00+00:00",
    "duration": 60,
    "current_step": "completed",
    "progress": 100,
    "final_state": "completed",
    "error": "",
    "logs": [],
}


class OperationalHistorySharedTests(unittest.TestCase):
    def test_snapshot_uses_same_completed_and_error_buckets(self):
        rows = [
            {**NORMALIZED_ITEM, "id": "1", "bucket": "completed", "state": "completed"},
            {**NORMALIZED_ITEM, "id": "2", "bucket": "completed", "state": "rolled_back"},
            {**NORMALIZED_ITEM, "id": "3", "bucket": "errors", "state": "error"},
            {**NORMALIZED_ITEM, "id": "4", "bucket": "other", "state": "running"},
        ]
        with patch.object(shared, "_addition_rows", return_value=rows):
            payload = shared._snapshot("addition")
        self.assertEqual(payload["counts"], {"completed": 2, "errors": 1})
        self.assertEqual(payload["total"], 4)

    def test_update_and_addition_return_the_same_normalized_schema(self):
        addition = dict(NORMALIZED_ITEM)
        update = {**NORMALIZED_ITEM, "operation_type": "update"}
        with (
            patch.object(shared, "_addition_rows", return_value=[addition]),
            patch.object(shared, "_update_rows", return_value=[update]),
        ):
            addition_payload = shared._snapshot("addition")
            update_payload = shared._snapshot("update")
        self.assertEqual(set(addition_payload), set(update_payload))
        self.assertEqual(set(addition_payload["items"][0]), set(update_payload["items"][0]))
        self.assertEqual(
            set(addition_payload),
            {"ok", "kind", "items", "total", "counts"},
        )

    def test_addition_snapshot_preserves_persisted_error_reconciliation(self):
        source = Path("app/operational_history_shared_policy.py").read_text(encoding="utf-8")
        self.assertIn("reliability._backfill_terminal_addition_history()", source)
        self.assertIn("addition_attempt_history", source)

    def test_invalid_history_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            shared._snapshot("qualquer")

    def test_only_one_structural_renderer_and_two_declarative_hosts_exist(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        update_html = Path("app/web.py").read_text(encoding="utf-8")
        addition_html = Path("app/static/addition_operational_ui.js").read_text(encoding="utf-8")
        panel = Path("app/static/panel.js").read_text(encoding="utf-8")

        self.assertEqual(script.count("function renderOperationalHistory("), 1)
        self.assertEqual(script.count("function renderHistoryRow("), 1)
        self.assertIn('data-operational-history-host data-history-type="update"', update_html)
        self.assertIn('data-operational-history-host data-history-type="addition"', addition_html)
        self.assertNotIn("op-history-compat", script)
        self.assertNotIn("compatibilityMarkup", script)
        self.assertNotIn("renderUpdateHistory", panel)
        self.assertNotIn("renderHistory()", addition_html)

    def test_legacy_history_ids_are_absent_from_consumers_and_alignment_layers(self):
        paths = (
            "app/web.py",
            "app/static/panel.js",
            "app/static/addition_operational_ui.js",
            "app/static/operational_ui_final_alignment.js",
            "app/static/operational_ui_consistency_v4.js",
            "app/static/operational_ui_card_size_parity_v6.js",
        )
        combined = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
        for legacy in (
            "updates_history_accordion",
            "addition_history_accordion",
            "updates_history_completed",
            "updates_history_errors",
            "addition_history_rows",
            "addition_history_refresh",
            "addition_history_tabs",
        ):
            self.assertNotIn(legacy, combined)

    def test_shared_component_contains_all_requested_controls(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        for token in (
            "data-history-search",
            "data-history-status",
            "data-history-origin",
            "data-history-sort",
            "data-history-date-from",
            "data-history-date-to",
            "data-history-last-days",
            'data-history-tab="completed"',
            'data-history-tab="errors"',
            "data-history-page-size",
            'data-history-action="prev"',
            "data-history-page",
            'data-history-action="next"',
            'data-history-action="download"',
            'data-history-action="refresh"',
            'data-history-action="delete"',
        ):
            self.assertIn(token, script)

    def test_shared_history_adds_no_background_activity(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("setInterval", script)
        self.assertNotIn("requestAnimationFrame", script)

    def test_shared_css_is_the_only_history_component_stylesheet(self):
        css = Path("app/static/operational_history_shared.css").read_text(encoding="utf-8")
        panel_css = Path("app/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".cs-history", css)
        self.assertIn("background:none!important", css)
        self.assertNotIn("#tab_panel_atualizacoes", css)
        self.assertNotIn("#tab_panel_adicoes", css)
        self.assertNotIn("updates-history", panel_css)


if __name__ == "__main__":
    unittest.main()
