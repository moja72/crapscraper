from __future__ import annotations

import unittest

import app.addition_pack_ignore_policy as policy


class AdditionPackIgnorePolicyTests(unittest.TestCase):
    def test_exact_plugintheme_pack_is_ignored(self) -> None:
        self.assertTrue(policy.is_ignored_pack({
            "source_name": "500 CodeCanyon Plugins",
            "source_product_url": "https://plugintheme.net/pt-BR/product/500-codecanyon-plugins",
        }))

    def test_same_name_outside_plugintheme_is_not_forced_ignored(self) -> None:
        self.assertFalse(policy.is_ignored_pack({
            "source_name": "500 CodeCanyon Plugins",
            "source_product_url": "https://example.com/500-codecanyon-plugins",
        }))

    def test_regular_plugintheme_plugin_is_not_ignored(self) -> None:
        self.assertFalse(policy.is_ignored_pack({
            "source_name": "AffiliateWP WordPress Plugin",
            "source_product_url": "https://plugintheme.net/pt-BR/product/affiliatewp-wordpress-plugin",
        }))


if __name__ == "__main__":
    unittest.main()
