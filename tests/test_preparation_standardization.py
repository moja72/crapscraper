from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.preparation_standardization_policy as policy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "static" / "preparation_standardization_v13.js"


class PreparationStandardizationTests(unittest.TestCase):
    def test_render_injects_only_canonical_v13_script(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda: "<html><body>painel</body></html>"
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original

        self.assertIn("data-preparation-standardization-v13", html)
        self.assertIn("cs-prep-v13-toolbar", html)
        self.assertIn("addition_preparation_select_all", html)
        self.assertNotIn("data-preparation-standardization-v12", html)

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

    def test_both_tabs_use_the_same_canonical_structure_and_order(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        required = [
            "cs-prep-v13-description",
            "cs-prep-v13-toolbar",
            "cs-prep-v13-advanced",
            "cs-prep-v13-meta",
            "cs-prep-v13-bulk",
            "cs-prep-v13-list",
            "cs-prep-v13-pagination",
            "addition_preparation_version",
            "addition_preparation_relationship",
            "Selecionar todo resultado",
            "Limpar seleção",
        ]
        for value in required:
            self.assertIn(value, script)

        update_order = "[description, toolbar, advanced, meta, bulk, progress, list, pagination]"
        addition_order = "[description, toolbar, advanced, meta, bulk, feedback, list, pagination]"
        self.assertIn(update_order, script)
        self.assertIn(addition_order, script)

    def test_addition_deduplicates_clear_selection_and_legacy_bodies(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('clean(button.textContent).toLowerCase() === "limpar seleção"', script)
        self.assertIn("removeLegacyBodies", script)
        self.assertIn("cs_addition_preparation_v13_body", script)
        self.assertIn("cs_updates_preparation_v13_body", script)
        self.assertIn("body.className = \"cs-prep-v13-body\"", script)

    def test_update_empty_state_is_deduplicated(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("function removeDuplicateEmpty", script)
        self.assertIn("if (seen.has(key)) node.remove()", script)
        self.assertIn("removeDuplicateEmpty(list)", script)

    def test_bulk_actions_are_purple_and_individual_actions_remain_green(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("linear-gradient(135deg,#7c3aed,#6d28d9)", script)
        self.assertIn(".update-prepare.btn-success", script)
        self.assertIn(".addition-op-actions .btn-success", script)
        self.assertIn("background:var(--success)!important", script)

    def test_addition_page_and_all_results_selection_are_supported(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('target.id === "addition_preparation_select_all"', script)
        self.assertIn('target.id === "cs_addition_select_all_results"', script)
        self.assertIn('box.dispatchEvent(new Event("change", {bubbles:true}))', script)
        self.assertIn("fetchAllAdditionIds", script)


if __name__ == "__main__":
    unittest.main()
