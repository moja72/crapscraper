from __future__ import annotations

import unittest


class InstalledContractChainTests(unittest.TestCase):
    def test_fallback_installer_mentions_final_contract_policies(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "app" / "addition_official_resolution_fallback_policy.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("install_addition_product_contract_policy()", text)
        self.assertIn("install_comparison_operation_status_policy()", text)
        self.assertLess(
            text.index("install_addition_full_product_integrity_policy()"),
            text.index("install_addition_product_contract_policy()"),
        )


if __name__ == "__main__":
    unittest.main()
