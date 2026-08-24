from __future__ import annotations

import unittest
from pathlib import Path


class HistoryRuntimeRemountContractTests(unittest.TestCase):
    def test_addition_history_is_repaired_after_legacy_rerender(self) -> None:
        script = Path("app/static/operational_history_shared.js").read_text(encoding="utf-8")
        for token in [
            'addition: { root: "#addition_history_accordion"',
            'data-oh-shell-version',
            'canonicalPresent',
            'ensureMounted("addition")',
            'MutationObserver',
            'data-oh-filter="sort"',
            'data-oh-filter="date-from"',
            'data-oh-filter="date-to"',
            'data-oh-filter="last-days"',
        ]:
            self.assertIn(token, script)

    def test_active_history_tab_has_no_legacy_bottom_indicator(self) -> None:
        css = Path("app/static/history_standardization_v2.css").read_text(encoding="utf-8")
        self.assertIn(".op-history-tab::before", css)
        self.assertIn(".op-history-tab::after", css)
        self.assertIn("content:none!important", css)
        self.assertIn("border-bottom-color:transparent!important", css)
        self.assertIn("box-shadow:none!important", css)


if __name__ == "__main__":
    unittest.main()
