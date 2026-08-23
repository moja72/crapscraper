from __future__ import annotations

import unittest

import app.addition_download_contract_policy as policy


class AdditionDownloadContractPolicyTests(unittest.TestCase):
    def test_download_name_uses_human_product_title(self):
        job = {
            "title": "Act Now - Social Activism &amp; NGO WordPress Theme",
            "source_name": "fallback",
        }
        self.assertEqual(
            policy._download_name(job),
            "Act Now - Social Activism & NGO WordPress Theme",
        )

    def test_download_file_uses_internal_server_path(self):
        job = {
            "zip_name": "act-now-social-activism-ngo-wordpress-theme-1-0-3.zip",
        }
        self.assertEqual(
            policy._download_file_path(job),
            "/home/plugintema.com/downloads/act-now-social-activism-ngo-wordpress-theme-1-0-3.zip",
        )

    def test_annual_variation_requires_365_day_expiry(self):
        variation = {
            "id": 10,
            "name": "Produto - 1 ano",
            "attributes": [{"option": "1 ano"}],
            "download_expiry": 365,
            "downloads": [{
                "name": "Produto",
                "file": "/home/plugintema.com/downloads/produto.zip",
            }],
        }
        self.assertTrue(
            policy._variation_matches_contract(
                variation,
                title="Produto",
                file_path="/home/plugintema.com/downloads/produto.zip",
            )
        )
        variation["download_expiry"] = -1
        self.assertFalse(
            policy._variation_matches_contract(
                variation,
                title="Produto",
                file_path="/home/plugintema.com/downloads/produto.zip",
            )
        )

    def test_payload_keeps_lifetime_unlimited_and_sets_annual_expiry(self):
        annual = policy._variation_payload(
            "annual",
            "Produto",
            "/home/plugintema.com/downloads/produto.zip",
        )
        lifetime = policy._variation_payload(
            "lifetime",
            "Produto",
            "/home/plugintema.com/downloads/produto.zip",
        )
        self.assertEqual(annual["download_expiry"], 365)
        self.assertNotIn("download_expiry", lifetime)
        self.assertEqual(annual["downloads"][0]["name"], "Produto")
        self.assertEqual(
            annual["downloads"][0]["file"],
            "/home/plugintema.com/downloads/produto.zip",
        )


if __name__ == "__main__":
    unittest.main()
