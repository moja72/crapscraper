from __future__ import annotations

import unittest

import app.update_cross_source_latest_policy as policy


class UpdateCrossSourceLatestPolicyTests(unittest.TestCase):
    def test_numeric_versions_compare_with_different_widths(self) -> None:
        self.assertTrue(policy._is_newer("2.35.10", "2.35.2"))
        self.assertTrue(policy._is_newer("2.36", "2.35.9"))
        self.assertFalse(policy._is_newer("2.35.2", "2.35.2"))
        self.assertFalse(policy._is_newer("2.35", "2.35.0"))

    def test_version_text_normalizes_prefixed_values(self) -> None:
        self.assertEqual(policy._version_text("v2.36.1"), "2.36.1")
        self.assertEqual(policy._version_text("Versão 2.35.2"), "2.35.2")

    def test_source_detection(self) -> None:
        self.assertEqual(
            policy._source_name("https://plugintheme.net/pt-BR/product/affiliatewp-wordpress-plugin"),
            "PluginTheme",
        )
        self.assertEqual(
            policy._source_name("https://www.ultrapackv2.com/item/affiliatewp-wordpress-plugin/"),
            "UltraPackV2",
        )

    def test_name_normalization_matches_affiliatewp_variants(self) -> None:
        self.assertEqual(
            policy._name_key("AffiliateWP WordPress Plugin"),
            policy._name_key("AffiliateWP Plugin"),
        )


if __name__ == "__main__":
    unittest.main()
