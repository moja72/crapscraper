from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_custom_fields_policy as policy


class _Woo:
    def __init__(self) -> None:
        self.meta_data = []

    def get_product_fresh(self, _product_id: int):
        return {"id": 123, "meta_data": list(self.meta_data)}


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

    def test_apply_writes_exact_custom_field_keys(self) -> None:
        job = {
            "woo_product_id": 123,
            "source_official_url": "https://example.dev/plugin/",
            "source_product_url": "https://www.ultrapackv2.com/item/example/",
            "developer": "Example Dev",
        }
        woo = _Woo()

        def fake_request(_woo, method, path, payload):
            self.assertEqual(method, "PUT")
            self.assertEqual(path, "/wp-json/wc/v3/products/123")
            woo.meta_data = [
                {"key": item["key"], "value": item["value"]}
                for item in payload.get("meta_data", [])
            ]
            return {"id": 123, "meta_data": woo.meta_data}

        with (
            patch.object(policy.additions, "_row", return_value=job),
            patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=woo),
            patch.object(policy.additions, "_wc_request", side_effect=fake_request),
            patch.object(policy.one_click, "_emit"),
        ):
            policy._apply_custom_fields("job")

        values = {item["key"]: item["value"] for item in woo.meta_data}
        self.assertEqual(values["site_oficial"], "https://example.dev/plugin/")
        self.assertEqual(values["desenvolvedor"], "Example Dev")


if __name__ == "__main__":
    unittest.main()
