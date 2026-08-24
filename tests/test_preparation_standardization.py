from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.preparation_standardization_policy as policy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "static" / "preparation_standardization_v12.js"
SELECTION_FIX = ROOT / "app" / "static" / "preparation_standardization_v12_selection_fix.js"


class PreparationStandardizationTests(unittest.TestCase):
    def test_render_injects_both_final_scripts(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda: "<html><body>painel</body></html>"
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original

        self.assertIn('data-preparation-standardization-v12="1"', html)
        self.assertIn('data-preparation-standardization-v12="2"', html)
        self.assertIn("cs-prep-v12-toolbar", html)
        self.assertIn("addition_preparation_select_all", html)

    def test_advanced_addition_filters_are_forwarded_to_server_side_pagination(self) -> None:
        captured: dict[str, object] = {}

        def fake_page(**kwargs):
            captured.update(kwargs)
            return {"items": [], "total": 0, "page": 1, "page_size": 5, "pages": 1}

        original = policy._BASE_OPERATIONS_PAYLOAD
        try:
            policy._BASE_OPERATIONS_PAYLOAD = lambda query: {"ok": True, "delegated": query}
            with patch.object(policy, "_filtered_preparation_page", side_effect=fake_page):
                payload = policy._patched_operations_payload(
                    "scope=preparation&q=yoast&state=waiting&version=missing_version&relationship=new_product&page=2&page_size=20"
                )
        finally:
            policy._BASE_OPERATIONS_PAYLOAD = original

        self.assertTrue(payload["ok"])
        self.assertEqual(captured["q"], "yoast")
        self.assertEqual(captured["state"], "waiting")
        self.assertEqual(captured["version"], "missing_version")
        self.assertEqual(captured["relationship"], "new_product")
        self.assertEqual(captured["page"], 2)
        self.assertEqual(captured["page_size"], 20)

    def test_shared_dom_contract_contains_requested_order_and_controls(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        required = [
            "cs-prep-v12-description",
            "cs-prep-v12-toolbar",
            "addition_preparation_version",
            "addition_preparation_relationship",
            "Selecionar todo resultado",
            "Limpar seleção",
            "cs-prep-v12-meta",
            "cs-prep-v12-list",
            "cs-prep-v12-pagination",
        ]
        for value in required:
            self.assertIn(value, script)

        update_order = "[description, toolbar, advanced, bulk, meta, progress, list, pagination]"
        addition_order = "[description, toolbar, advanced, bulk, meta, feedback, list, pagination]"
        self.assertIn(update_order, script)
        self.assertIn(addition_order, script)

    def test_update_empty_state_is_deduplicated_and_legacy_bottom_hint_removed(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("function removeDuplicateUpdateEmpty", script)
        self.assertIn("if (seen.has(key)) node.remove()", script)
        self.assertIn(".cs-v4-preparation-hint", script)
        self.assertIn("node.remove()", script)

    def test_addition_page_selection_bridge_keeps_original_private_set_in_sync(self) -> None:
        script = SELECTION_FIX.read_text(encoding="utf-8")
        self.assertIn('target.id === "addition_preparation_select_all"', script)
        self.assertIn('box.dispatchEvent(new Event("change", {bubbles:true}))', script)
        self.assertIn('all.checked = false', script)


if __name__ == "__main__":
    unittest.main()
