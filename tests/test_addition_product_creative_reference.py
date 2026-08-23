from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.addition_product_creative_policy as creative


class AdditionProductCreativeReferenceTests(unittest.TestCase):
    def test_missing_reference_does_not_abort_image_request(self):
        sent = {}

        def fake_send(page, prompt, job_id):
            sent["prompt"] = prompt
            sent["job_id"] = job_id
            return 1, {"asset-1"}

        job = {
            "kind": "theme",
            "title": "Tema teste",
            "source_product_url": "https://example.test/source",
            "source_official_url": "https://example.test/official",
        }

        previous_send = creative._BASE_SEND_MESSAGE
        creative._BASE_SEND_MESSAGE = fake_send
        try:
            with patch.object(creative.additions, "_row", return_value=job), \
                 patch.object(creative, "_reference_path", return_value=Path("missing/exemplo tema.webp")), \
                 patch.object(creative.one_click, "_emit", return_value=None):
                result = creative._patched_send_message(
                    None,
                    "Agora gere somente a imagem final do produto",
                    "job-1",
                )
        finally:
            creative._BASE_SEND_MESSAGE = previous_send

        self.assertEqual(result, (1, {"asset-1"}))
        self.assertEqual(sent["job_id"], "job-1")
        self.assertIn("não há mockup local anexado", sent["prompt"].lower())
        self.assertNotIn("use o arquivo anexado", sent["prompt"].lower())
        self.assertNotIn("referência visual obrigatória", sent["prompt"].lower())

    def test_failed_attachment_falls_back_to_attachment_free_prompt(self):
        sent = {}

        def fake_send(page, prompt, job_id):
            sent["prompt"] = prompt
            return 2, set()

        job = {"kind": "plugin", "title": "Plugin teste"}
        previous_send = creative._BASE_SEND_MESSAGE
        creative._BASE_SEND_MESSAGE = fake_send
        try:
            with patch.object(creative.additions, "_row", return_value=job), \
                 patch.object(creative, "_reference_path", return_value=Path("app/static/exemplo plugin.webp")), \
                 patch.object(creative, "_attach_reference", return_value=False):
                result = creative._patched_send_message(
                    object(),
                    "Agora gere somente a imagem final do produto",
                    "job-2",
                )
        finally:
            creative._BASE_SEND_MESSAGE = previous_send

        self.assertEqual(result, (2, set()))
        self.assertIn("não há mockup local anexado", sent["prompt"].lower())
        self.assertNotIn("use o arquivo anexado", sent["prompt"].lower())


if __name__ == "__main__":
    unittest.main()
