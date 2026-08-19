from __future__ import annotations

import unittest
from unittest.mock import patch

import app.comparison_operation_status_policy as policy


class ComparisonOperationStatusPolicyTests(unittest.TestCase):
    def test_generic_origin_text_removes_ultrapack_brand(self):
        self.assertEqual(policy._generic_origin_text("Novo no Ultrapack"), "Novo")
        text = policy._generic_origin_text("Versão do Ultrapack não confiável")
        self.assertIn("site de origem", text)
        self.assertNotIn("Ultrapack", text)

    def test_completed_addition_becomes_added(self):
        full = {
            "rows": [{
                "comparison_item_id": "comparison-1",
                "status": "new_source",
                "status_label": "Novo no Ultrapack",
                "status_reason": "O produto foi encontrado no Ultrapack.",
            }],
            "counts": {"new_source": 1},
        }
        with patch.object(policy, "_operation_overrides", return_value={
            "comparison-1": {
                "completed_at": "2026-08-19T20:00:00+00:00",
                "status": "added",
                "status_label": "Adicionado",
                "status_reason": "Produto adicionado ao site.",
                "version": "1.2.3",
            }
        }):
            result = policy._apply_operation_status(full)
        self.assertEqual(result["rows"][0]["status"], "added")
        self.assertEqual(result["rows"][0]["status_label"], "Adicionado")
        self.assertEqual(result["rows"][0]["site_version"], "1.2.3")
        self.assertEqual(result["counts"]["added"], 1)
        self.assertEqual(result["counts"]["new_source"], 0)

    def test_completed_update_becomes_updated(self):
        full = {"rows": [{"comparison_item_id": "comparison-2", "status": "update_available"}]}
        with patch.object(policy, "_operation_overrides", return_value={
            "comparison-2": {
                "completed_at": "2026-08-19T20:00:00+00:00",
                "status": "updated",
                "status_label": "Atualizado",
                "status_reason": "Atualização concluída com sucesso no site.",
                "version": "2.0.0",
            }
        }):
            result = policy._apply_operation_status(full)
        self.assertEqual(result["rows"][0]["status"], "updated")
        self.assertEqual(result["rows"][0]["site_version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
