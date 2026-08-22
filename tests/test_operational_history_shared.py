from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.operational_history_shared_policy as shared


class OperationalHistorySharedTests(unittest.TestCase):
    def test_snapshot_uses_same_completed_and_error_buckets(self):
        rows = [
            {"bucket": "completed", "status": "completed"},
            {"bucket": "completed", "status": "rolled_back"},
            {"bucket": "errors", "status": "error"},
            {"bucket": "other", "status": "running"},
        ]
        with patch.object(shared, "_addition_rows", return_value=rows):
            payload = shared._snapshot("addition")
        self.assertEqual(payload["counts"], {"completed": 2, "errors": 1})
        self.assertEqual(payload["total"], 4)

    def test_invalid_history_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            shared._snapshot("qualquer")

    def test_shared_component_contains_requested_filters(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        self.assertIn('type="date"', script)
        self.assertIn('data-oh-filter="last-days"', script)
        self.assertIn('Alfabética (A–Z)', script)
        self.assertIn('Alfabética inversa (Z–A)', script)
        self.assertIn('function shell(kind)', script)
        self.assertIn('mount("update")', script)
        self.assertIn('mount("addition")', script)

    def test_shared_history_does_not_add_polling_or_mutation_observer(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("setInterval", script)

    def test_shared_css_targets_both_history_roots_through_one_component(self):
        css = Path("app/static/operational_history_shared.css").read_text(encoding="utf-8")
        self.assertIn(".operational-history-shared", css)
        self.assertNotIn("#updates_history_accordion", css)
        self.assertNotIn("#addition_history_accordion", css)


if __name__ == "__main__":
    unittest.main()
