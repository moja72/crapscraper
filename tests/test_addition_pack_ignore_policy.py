from __future__ import annotations

import unittest

import app.addition_pack_ignore_policy as policy


class AdditionPackIgnorePolicyTests(unittest.TestCase):
    def test_exact_pack_is_ignored_with_plugintheme_url(self) -> None:
        self.assertTrue(policy.is_ignored_pack({
            "source_name": "500 CodeCanyon Plugins",
            "source_product_url": "https://plugintheme.net/pt-BR/product/500-codecanyon-plugins",
        }))

    def test_exact_pack_is_ignored_even_when_old_record_has_no_url(self) -> None:
        self.assertTrue(policy.is_ignored_pack({
            "source_name": "500 CodeCanyon Plugins",
            "source_product_url": "",
        }))

    def test_exact_pack_name_is_business_rule_not_origin_heuristic(self) -> None:
        self.assertTrue(policy.is_ignored_pack({
            "title": "500 CodeCanyon Plugins",
            "source_product_url": "https://example.com/500-codecanyon-plugins",
        }))

    def test_regular_plugintheme_plugin_is_not_ignored(self) -> None:
        self.assertFalse(policy.is_ignored_pack({
            "source_name": "AffiliateWP WordPress Plugin",
            "source_product_url": "https://plugintheme.net/pt-BR/product/affiliatewp-wordpress-plugin",
        }))


if __name__ == "__main__":
    unittest.main()
