from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_custom_fields_policy as policy


class AdditionCustomFieldsPolicyTests(unittest.TestCase):
    def test_official_url_rejects_origin_site(self) -> None:
        job = {
            "source_official_url": "https://www.ultrapackv2.com/item/example/",
            "source_product_url": "https://www.ultrapackv2.com/item/example/",
        }
        with patch.object(policy, "_fetch_html", return_value=""):
            self.assertEqual(policy._official_url(job), "")

    def test_official_url_accepts_external_product_page(self) -> None:
        job = {
            "source_official_url": "https://codecanyon.net/item/example-plugin/123456",
            "source_product_url": "https://www.ultrapackv2.com/item/example/",
        }
        self.assertEqual(
            policy._official_url(job),
            "https://codecanyon.net/item/example-plugin/123456",
        )

    def test_developer_is_read_from_json_ld(self) -> None:
        html = '''
        <script type="application/ld+json">
        {"@type":"SoftwareApplication","author":{"@type":"Organization","name":"Example Dev"}}
        </script>
        '''
        self.assertEqual(policy._developer_from_html(html), "Example Dev")

    def test_developer_is_read_from_envato_user_link(self) -> None:
        html = '<a href="https://codecanyon.net/user/awesomeauthor">AwesomeAuthor</a>'
        self.assertEqual(policy._developer_from_html(html), "AwesomeAuthor")

    def test_non_marketplace_domain_can_be_used_as_brand_fallback(self) -> None:
        self.assertEqual(policy._domain_developer("https://elementor.com/pro/"), "Elementor")


if __name__ == "__main__":
    unittest.main()
