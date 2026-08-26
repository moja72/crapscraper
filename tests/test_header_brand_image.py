from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

import app.process_observability_policy as policy


class HeaderBrandImageTests(unittest.TestCase):
    def test_header_text_is_replaced_by_local_webp_without_extra_route(self) -> None:
        original_path = policy._BRAND_IMAGE_PATH
        sample = (
            '<html><head></head><body>'
            '<div class="page-brand-title-row"><h1>CrapScraper</h1>'
            '<img class="page-brand-title-image" src="/emoji.webp" alt=""></div>'
            '</body></html>'
        )
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "CrapScraper.webp"
            image_bytes = b"RIFFfake-webp-for-test"
            image_path.write_bytes(image_bytes)
            policy._BRAND_IMAGE_PATH = image_path
            try:
                rendered = policy._apply_header_brand_image(sample)
            finally:
                policy._BRAND_IMAGE_PATH = original_path

        expected = base64.b64encode(image_bytes).decode("ascii")
        self.assertNotIn("<h1>CrapScraper</h1>", rendered)
        self.assertNotIn("page-brand-title-image", rendered)
        self.assertIn('class="page-brand-logo"', rendered)
        self.assertIn(f"data:image/webp;base64,{expected}", rendered)
        self.assertEqual(rendered.count("data-crapscraper-brand-image"), 1)

    def test_missing_local_logo_keeps_existing_header(self) -> None:
        original_path = policy._BRAND_IMAGE_PATH
        sample = '<div class="page-brand-title-row"><h1>CrapScraper</h1></div>'
        policy._BRAND_IMAGE_PATH = Path("definitely-missing-CrapScraper.webp")
        try:
            rendered = policy._apply_header_brand_image(sample)
        finally:
            policy._BRAND_IMAGE_PATH = original_path
        self.assertEqual(rendered, sample)


if __name__ == "__main__":
    unittest.main()
