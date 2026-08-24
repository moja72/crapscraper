from __future__ import annotations

import unittest
from pathlib import Path


class HistoryStandardizationV2Tests(unittest.TestCase):
    def test_shared_history_is_installed_as_final_visual_layer(self):
        source = Path("app/process_modal_stability_policy.py").read_text(encoding="utf-8")
        self.assertIn("install_history_standardization_policy", source)
        self.assertGreater(
            source.rfind("install_history_standardization_policy()"),
            source.rfind("web.render_panel_page = _patched_render_panel_page"),
        )

    def test_history_policy_injects_existing_shared_component(self):
        source = Path("app/history_standardization_policy.py").read_text(encoding="utf-8")
        self.assertIn("install_operational_history_shared_policy()", source)
        self.assertIn("operational_history_shared.css", source)
        self.assertIn("operational_history_shared.js", source)
        self.assertIn("history_standardization_v2.css", source)

    def test_both_histories_have_sort_and_period_filters(self):
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        self.assertIn('data-oh-filter="sort"', script)
        self.assertIn('data-oh-filter="date-from"', script)
        self.assertIn('data-oh-filter="date-to"', script)
        self.assertIn('data-oh-filter="last-days"', script)
        self.assertIn('data-oh-action="last-days"', script)
        self.assertIn('data-oh-action="clear-period"', script)
        self.assertNotIn(
            "Consulte tentativas anteriores, resultados, duração e registros persistidos de cada cadastro",
            script,
        )

    def test_shared_visual_contract_uses_large_actions_and_same_tabs(self):
        css = Path("app/static/history_standardization_v2.css").read_text(encoding="utf-8")
        self.assertIn(".op-history-actions button", css)
        self.assertIn("min-height:40px!important", css)
        self.assertIn(".op-history-period button", css)
        self.assertIn(".op-history-tab.is-active", css)
        self.assertIn("border-radius:9px 9px 0 0!important", css)


if __name__ == "__main__":
    unittest.main()
