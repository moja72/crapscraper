from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_developer_resolution_fix_policy as policy


class AdditionDeveloperResolutionFixPolicyTests(unittest.TestCase):
    def test_reseller_is_never_valid_developer(self) -> None:
        self.assertTrue(policy._is_reseller_developer("PluginTheme.net"))
        self.assertTrue(policy._is_reseller_developer("UltraPackV2"))
        self.assertFalse(policy._is_reseller_developer("designThemes"))

    def test_codecanyon_aggregate_uses_market_brand_not_reseller(self) -> None:
        job = {
            "source_name": "500 CodeCanyon Plugins",
            "desenvolvedor": "PluginTheme.net",
        }
        self.assertTrue(policy._is_codecanyon_aggregate(job))
        self.assertEqual(
            policy._developer(job, "https://codecanyon.net/"),
            "CodeCanyon / Envato Market",
        )

    def test_normal_product_drops_reseller_result(self) -> None:
        job = {"source_name": "Example Plugin"}
        with patch.object(policy, "_BASE_DEVELOPER", lambda _job, _official: "PluginTheme.net"):
            self.assertEqual(policy._developer(job, "https://example.com"), "")

    def test_revalidation_replaces_persisted_wrong_developer(self) -> None:
        row = {
            "source_name": "500 CodeCanyon Plugins",
            "source_official_url": "https://codecanyon.net/",
            "desenvolvedor": "PluginTheme.net",
        }
        with (
            patch.object(policy.additions, "_row", return_value=row),
            patch.object(policy.fields, "_developer", return_value="CodeCanyon / Envato Market"),
            patch.object(policy.operational, "_update_operation") as update,
            patch.object(policy.one_click, "_emit"),
        ):
            policy._resolve_developer_fields("job-1")

        update.assert_called_once_with(
            "job-1",
            site_oficial="https://codecanyon.net/",
            desenvolvedor="CodeCanyon / Envato Market",
        )


if __name__ == "__main__":
    unittest.main()
