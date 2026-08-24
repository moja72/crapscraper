from __future__ import annotations

import unittest

import app.addition_download_contract_v2_policy as policy


class AdditionDownloadContractV2PolicyTests(unittest.TestCase):
    def test_target_file_prefers_existing_woocommerce_filename(self):
        job = {"zip_name": "source-package.zip"}
        variations = [{
            "downloads": [{
                "name": "old",
                "file": "https://plugintema.com.br/downloads/act-now-social-activism-ngo-wordpress-theme-1-0-3.zip",
            }],
        }]
        self.assertEqual(
            policy._target_file_path(job, variations),
            "/home/plugintema.com/downloads/act-now-social-activism-ngo-wordpress-theme-1-0-3.zip",
        )

    def test_server_confirmation_accepts_exact_annual_contract(self):
        row = {
            "period": "annual",
            "name": "Act Now - Social Activism & NGO WordPress Theme",
            "file": "/home/plugintema.com/downloads/act-now.zip",
            "expiry": "365",
            "downloadable": "yes",
            "virtual": "yes",
        }
        self.assertTrue(
            policy._server_row_matches(
                row,
                title="Act Now - Social Activism & NGO WordPress Theme",
                file_path="/home/plugintema.com/downloads/act-now.zip",
            )
        )

    def test_server_confirmation_requires_lifetime_without_expiry(self):
        row = {
            "period": "lifetime",
            "name": "Produto",
            "file": "/home/plugintema.com/downloads/produto.zip",
            "expiry": "-1",
            "downloadable": "yes",
            "virtual": "yes",
        }
        self.assertTrue(
            policy._server_row_matches(
                row,
                title="Produto",
                file_path="/home/plugintema.com/downloads/produto.zip",
            )
        )
        row["expiry"] = "365"
        self.assertFalse(
            policy._server_row_matches(
                row,
                title="Produto",
                file_path="/home/plugintema.com/downloads/produto.zip",
            )
        )

    def test_postmeta_program_writes_downloadable_files_directly(self):
        program = policy._postmeta_program("Zm9v")
        self.assertIn("_downloadable_files", program)
        self.assertIn("update_post_meta", program)
        self.assertIn("_download_expiry", program)


if __name__ == "__main__":
    unittest.main()
