from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_latest_source_does_not_overwrite_approved_snapshot(self) -> None:
        job = SimpleNamespace(
            queue_type="update",
            relationship="safe_auto",
            woo_product_id=89674,
            name="AffiliateWP WordPress Plugin",
            official_url="https://affiliatewp.com/",
            ultrapack_url="https://plugintheme.net/product/affiliatewp",
            ultrapack_version="2.35.2",
            approved_source_version="2.35.2",
            effective_source_version="",
            source_name="PluginTheme",
        )
        service = SimpleNamespace(
            woo=SimpleNamespace(get_product_fresh=lambda _product_id: {}),
            logger=lambda _message: None,
        )
        rows = [{
            "source_name": "AffiliateWP WordPress Plugin",
            "source_version": "2.36.0",
            "source_product_url": "https://www.ultrapackv2.com/item/affiliatewp/",
            "source_official_url": "https://affiliatewp.com/",
            "relationship_state": "safe_auto",
        }]
        with (
            patch.object(policy, "pt_versao", return_value="2.35.4"),
            patch.object(policy, "_candidate_rows", return_value=rows),
            patch.object(policy, "_inspect_candidate", return_value="2.36.0"),
        ):
            policy._select_latest_source(service, job)

        self.assertEqual(job.approved_source_version, "2.35.2")
        self.assertEqual(job.ultrapack_version, "2.36.0")
        self.assertEqual(job.ultrapack_url, rows[0]["source_product_url"])


if __name__ == "__main__":
    unittest.main()
