from __future__ import annotations

import unittest
from pathlib import Path

import app.operational_overview_standardization_policy as policy


class OperationalOverviewStandardizationTests(unittest.TestCase):
    @staticmethod
    def _script() -> str:
        return (
            Path(__file__).resolve().parents[1]
            / "app"
            / "static"
            / "operational_overview_standardization.js"
        ).read_text(encoding="utf-8")

    def test_render_changes_update_title_and_injects_final_script(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda: (
                '<html><body><div class="section-title">Atualizações</div>'
                '<div class="small">Prepare com segurança, revise o plano e execute sequencialmente.</div>'
                '</body></html>'
            )
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original

        self.assertIn("Atualiza produtos", html)
        self.assertIn("execute as atualizações com segurança no WooCommerce", html)
        self.assertIn("data-operational-overview-standardization", html)

    def test_final_script_preserves_operational_ids_and_removes_flow_strip(self) -> None:
        script = self._script()
        self.assertIn('#updates_refresh_btn', script)
        self.assertIn('#updates_summary', script)
        self.assertIn('#addition_sync_approved', script)
        self.assertIn('#addition_summary_grid', script)
        self.assertIn('flow.remove()', script)
        self.assertIn('Atualiza produtos', script)
        self.assertIn('Adicionar produtos', script)

    def test_main_sequence_is_heading_progress_cards_then_auxiliary_status(self) -> None:
        script = self._script()
        self.assertIn('ensureOrdered(card, [head, progress, summary, lock])', script)
        self.assertIn('ensureOrdered(content, [progress, grid, guidance])', script)
        self.assertIn('ensureOrdered(card, [head, content])', script)

    def test_normalizer_avoids_rewriting_equal_text(self) -> None:
        script = self._script()
        self.assertIn('normalize(node.textContent) !== value', script)
        self.assertIn('if (expected !== node) parent.insertBefore', script)


if __name__ == "__main__":
    unittest.main()
