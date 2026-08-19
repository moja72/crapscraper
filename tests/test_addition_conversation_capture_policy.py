from __future__ import annotations

import unittest

import app.addition_conversation_capture_policy as policy


class AdditionConversationCapturePolicyTests(unittest.TestCase):
    def test_resolves_themeforest_item_as_official(self) -> None:
        html = """
        <html><body>
          <a href="https://www.facebook.com/example">Facebook</a>
          <a href="https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701">Página do Item</a>
        </body></html>
        """
        resolved = policy._official_from_html(
            html,
            "https://www.ultrapackv2.com/item/123-medicine/",
        )
        self.assertEqual(
            resolved,
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )

    def test_rejects_ultrapack_as_official(self) -> None:
        self.assertFalse(
            policy._is_official_candidate(
                "https://www.ultrapackv2.com/item/example/",
                "https://www.ultrapackv2.com/item/example/",
            )
        )

    def test_description_prompt_only_exposes_official_page(self) -> None:
        prompt = policy._description_prompt(
            {
                "kind": "theme",
                "source_name": "123 Medicine",
                "source_version": "1.5.2",
                "source_product_url": "https://www.ultrapackv2.com/item/example/",
                "source_official_url": "https://themeforest.net/item/example/123",
            }
        )
        lowered = prompt.lower()
        self.assertIn("página oficial do produto", lowered)
        self.assertIn("themeforest.net/item/example/123", lowered)
        self.assertNotIn("ultrapackv2.com", lowered)
        self.assertNotIn("página da fonte", lowered)

    def test_image_prompt_only_exposes_official_page(self) -> None:
        prompt = policy._image_prompt(
            {
                "kind": "plugin",
                "source_name": "Example Plugin",
                "source_product_url": "https://www.ultrapackv2.com/item/example/",
                "source_official_url": "https://vendor.example/plugin/",
            }
        )
        lowered = prompt.lower()
        self.assertIn("página oficial do produto", lowered)
        self.assertIn("vendor.example/plugin", lowered)
        self.assertNotIn("ultrapackv2.com", lowered)
        self.assertIn("vitalício | ilimitado | atualizado", lowered)

    def test_user_image_candidate_is_rejected(self) -> None:
        score = policy._image_candidate_score(
            {"role": "user", "text": "", "width": 1024, "height": 1024}
        )
        self.assertLess(score, 0)

    def test_large_assistant_image_candidate_is_preferred(self) -> None:
        score = policy._image_candidate_score(
            {"role": "assistant", "text": "Worked for 2m", "width": 1024, "height": 1024}
        )
        self.assertGreater(score, 250)


if __name__ == "__main__":
    unittest.main()
