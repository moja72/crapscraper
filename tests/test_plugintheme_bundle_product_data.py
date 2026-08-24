from __future__ import annotations

import unittest

from app.integrations.plugintheme_download import PluginThemeDownloader


class PluginThemeBundleProductDataTests(unittest.TestCase):
    def test_uses_id_from_exact_bundle_object_not_nearest_child(self):
        bundle_id = "11111111-1111-1111-1111-111111111111"
        child_id = "22222222-2222-2222-2222-222222222222"
        html = (
            '<script>self.__next_f.push([1,"'
            '{\\"id\\":\\"' + bundle_id + '\\",'
            '\\"version\\":\\"1.0\\",'
            '\\"slug\\":\\"500-codecanyon-plugins\\",'
            '\\"items\\":[{\\"id\\":\\"' + child_id + '\\",'
            '\\"slug\\":\\"child-plugin\\",\\"version\\":\\"9.9\\"}]}'
            '"])</script>'
        )

        result = PluginThemeDownloader.product_data(
            "https://plugintheme.net/product/500-codecanyon-plugins",
            html,
        )

        self.assertEqual(result["id"], bundle_id)
        self.assertEqual(result["slug"], "500-codecanyon-plugins")
        self.assertEqual(result["version"], "1.0")

    def test_fallback_prefers_product_id_before_slug_over_child_after_slug(self):
        bundle_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        child_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        html = (
            f'"id":"{bundle_id}","version":"2.5","slug":"500-codecanyon-plugins",'
            f'BROKEN-RSC,"id":"{child_id}","version":"8.0","slug":"child"'
        )

        result = PluginThemeDownloader.product_data(
            "https://plugintheme.net/product/500-codecanyon-plugins",
            html,
        )

        self.assertEqual(result["id"], bundle_id)
        self.assertEqual(result["version"], "2.5")

    def test_rejects_page_without_exact_slug(self):
        with self.assertRaises(Exception):
            PluginThemeDownloader.product_data(
                "https://plugintheme.net/product/500-codecanyon-plugins",
                '{"id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","slug":"other-product"}',
            )


if __name__ == "__main__":
    unittest.main()
