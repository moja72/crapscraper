from __future__ import annotations

import unittest

import app.addition_official_resolution_fallback_policy as policy


class AdditionOfficialResolutionFallbackPolicyTests(unittest.TestCase):
    def test_detects_themeforest_from_ultrapack_slug(self) -> None:
        source = (
            "https://www.ultrapackv2.com/item/"
            "themeforest-hospitais-clinicas-123-medicine-pharmacy-shop-hospital-medical-health-service-theme/"
        )
        self.assertEqual(policy._marketplace_from_source(source), "themeforest")

    def test_extracts_serialized_themeforest_url(self) -> None:
        html = (
            '{"sale":"https:\\/\\/themeforest.net\\/item\\/'
            '123-medicine-pharmacy-shop-hospital-medical-health-service-theme\\/6552701"}'
        )
        rows = policy._extract_marketplace_candidates(html, "themeforest")
        urls = [url for url, _label in rows]
        self.assertIn(
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
            urls,
        )

    def test_unwraps_duckduckgo_redirect(self) -> None:
        wrapped = (
            "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fthemeforest.net%2Fitem%2F"
            "123-medicine-pharmacy-shop-hospital-medical-health-service-theme%2F6552701"
        )
        self.assertEqual(
            policy._unwrap_search_url(wrapped),
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )

    def test_rejects_preview_url(self) -> None:
        self.assertFalse(
            policy._marketplace_item_url(
                "https://themeforest.net/item/example/full_screen_preview/123",
                "themeforest",
            )
        )

    def test_name_similarity_accepts_correct_item(self) -> None:
        score = policy._name_similarity(
            "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )
        self.assertGreaterEqual(score, 0.9)

    def test_name_similarity_rejects_unrelated_item(self) -> None:
        score = policy._name_similarity(
            "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226",
        )
        self.assertLess(score, 0.5)

    def test_best_candidate_picks_matching_themeforest_item(self) -> None:
        document = """
        <a href="https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226">Avada</a>
        <a href="https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701">
            123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme
        </a>
        """
        result = policy._best_marketplace_candidate(
            "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "themeforest",
            [document],
        )
        self.assertEqual(
            result,
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )

    def test_extracts_third_party_result_from_bing_rss(self) -> None:
        rss = """
        <rss><channel><item>
          <title>123 Medicine Theme</title>
          <link>https://themes.example.test/123-medicine-theme</link>
        </item></channel></rss>
        """
        links = policy._extract_search_result_links(
            rss,
            "https://www.ultrapackv2.com/item/themeforest-123-medicine/",
            "themeforest",
        )
        self.assertIn("https://themes.example.test/123-medicine-theme", links)

    def test_indirect_page_can_reveal_official_sale_link(self) -> None:
        intermediary = """
        <h1>123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme</h1>
        <a href="https://1.envato.market/c/example?u=https%3A%2F%2Fthemeforest.net%2Fitem%2F123-medicine-pharmacy-shop-hospital-medical-health-service-theme%2F6552701">
          Order on ThemeForest
        </a>
        """
        result = policy._best_marketplace_candidate(
            "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "themeforest",
            [intermediary],
        )
        self.assertEqual(
            result,
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )

    def test_short_search_name_uses_product_prefix(self) -> None:
        self.assertEqual(
            policy._short_search_name(
                "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme"
            ),
            "123 Medicine",
        )


if __name__ == "__main__":
    unittest.main()
