from __future__ import annotations

import unittest

import app.addition_capture_pipeline_resilience_policy as policy


class AdditionCapturePipelineResiliencePolicyTests(unittest.TestCase):
    def test_limits_are_doubled_for_description_and_image(self) -> None:
        self.assertEqual(policy._DESCRIPTION_TIMEOUT_SECONDS, 600)
        self.assertEqual(policy._IMAGE_TIMEOUT_SECONDS, 960)
        self.assertEqual(policy._duration_label(600), "10m")
        self.assertEqual(policy._duration_label(960), "16m")

    def test_capture_pending_with_mapped_chats_is_recoverable(self) -> None:
        row = {
            "approval_active": 1,
            "queue_state": "error",
            "short_description": "Descrição comercial já capturada e persistida.",
            "description_chat_url": "https://chatgpt.com/c/description",
            "image_chat_url": "https://chatgpt.com/c/image",
            "image_path": "",
            "source_product_url": "https://example.test/product",
            "source_version": "1.0.0",
            "source_official_url": "https://example.test/official",
            "category_name": "",
            "annual_regular": "",
            "lifetime_regular": "",
            "zip_path": "",
            "zip_sha256": "",
        }
        self.assertTrue(policy._recoverable_capture_pending(row))

    def test_without_image_chat_is_not_capture_recoverable(self) -> None:
        row = {
            "approval_active": 1,
            "queue_state": "error",
            "short_description": "Descrição persistida.",
            "description_chat_url": "https://chatgpt.com/c/description",
            "image_chat_url": "",
            "image_path": "",
        }
        self.assertFalse(policy._recoverable_capture_pending(row))

    def test_attachment_claim_is_removed_when_no_reference_exists(self) -> None:
        source = (
            "Use o arquivo anexado apenas como referência de mockup. "
            "Gere uma nova imagem profissional."
        )
        cleaned = policy._strip_attachment_claims(source)
        self.assertNotIn("Use o arquivo anexado", cleaned)
        self.assertIn("Não há mockup local anexado", cleaned)


if __name__ == "__main__":
    unittest.main()
