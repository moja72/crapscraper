from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "static" / "operational_overview_standardization.js"


class OperationalOverviewGuidanceRemovalTests(unittest.TestCase):
    def test_both_redundant_notices_are_removed(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('$("#updates_execution_lock", card)?.remove()', script)
        self.assertIn('$("#addition_guidance", card)?.remove()', script)
        self.assertIn('#tab_panel_atualizacoes #updates_execution_lock', script)
        self.assertIn('#tab_panel_adicoes #addition_guidance{display:none!important}', script)


if __name__ == "__main__":
    unittest.main()
