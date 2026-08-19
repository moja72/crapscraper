from __future__ import annotations

import unittest

import app.addition_chat1_official_resolution_policy as policy


class AdditionChat1OfficialResolutionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job = {
            "kind": "theme",
            "source_name": "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "source_version": "1.5.2",
            "source_product_url": (
                "https://www.ultrapackv2.com/item/"
                "themeforest-hospitais-clinicas-123-medicine-pharmacy-shop-hospital-medical-health-service-theme/"
            ),
            "source_official_url": "",
        }

    def _description(self) -> str:
        return (
            "Crie um site de saúde claro e profissional com o 123 Medicine. "
            "O tema organiza páginas para clínicas, hospitais, farmácias e serviços médicos, ajudando a apresentar "
            "atendimentos, equipe, informações institucionais e produtos de forma coerente com o segmento. "
            "É indicado para projetos WordPress que precisam reunir conteúdo e serviços de saúde em uma estrutura organizada."
        )

    def test_prompt_does_not_expose_ultrapack_url(self) -> None:
        prompt = policy._description_prompt(self.job)
        lowered = prompt.lower()
        self.assertNotIn("ultrapackv2.com", lowered)
        self.assertIn("themeforest", lowered)
        self.assertIn("pagina_oficial:", lowered)
        self.assertIn("titulo_oficial:", lowered)
        self.assertIn("descricao:", lowered)

    def test_parses_official_url_title_and_description(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://themeforest.net/item/"
            "123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701\n"
            "TITULO_OFICIAL: 123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme\n"
            "DESCRICAO: " + self._description()
        )
        official, description = policy._parse_answer(raw, self.job)
        self.assertEqual(
            official,
            "https://themeforest.net/item/123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701",
        )
        self.assertGreater(len(description), 300)

    def test_accepts_real_themeforest_slug_when_title_confirms_identity(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701\n"
            "TITULO_OFICIAL: 123Medicine - eCommerce WordPress Theme\n"
            "DESCRICAO: " + self._description()
        )
        official, description = policy._parse_answer(raw, self.job)
        self.assertEqual(
            official,
            "https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701",
        )
        self.assertGreater(len(description), 300)

    def test_valid_official_accepts_compact_product_prefix(self) -> None:
        self.assertTrue(
            policy._valid_official(
                self.job,
                "https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701",
                "123Medicine - eCommerce WordPress Theme",
            )
        )

    def test_accepts_missing_title_when_url_itself_confirms_identity(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701\n"
            "DESCRICAO: " + self._description()
        )
        official, description = policy._parse_answer(raw, self.job)
        self.assertEqual(
            official,
            "https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701",
        )
        self.assertGreater(len(description), 300)

    def test_rejects_ultrapack_as_official_answer(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://www.ultrapackv2.com/item/example/\n"
            "TITULO_OFICIAL: 123 Medicine\n"
            "DESCRICAO: " + self._description()
        )
        self.assertEqual(policy._parse_answer(raw, self.job), ("", ""))

    def test_rejects_wrong_themeforest_item(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226\n"
            "TITULO_OFICIAL: Avada | Website Builder For WordPress & WooCommerce\n"
            "DESCRICAO: " + self._description()
        )
        self.assertEqual(policy._parse_answer(raw, self.job), ("", ""))

    def test_correct_title_cannot_rescue_unrelated_url(self) -> None:
        raw = (
            "PAGINA_OFICIAL: https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226\n"
            "TITULO_OFICIAL: 123Medicine - eCommerce WordPress Theme\n"
            "DESCRICAO: " + self._description()
        )
        self.assertEqual(policy._parse_answer(raw, self.job), ("", ""))

    def test_accepts_prevalidated_official_page_in_prompt(self) -> None:
        job = dict(self.job)
        job["source_official_url"] = (
            "https://themeforest.net/item/"
            "123-medicine-pharmacy-shop-hospital-medical-health-service-theme/6552701"
        )
        prompt = policy._description_prompt(job)
        self.assertIn("A página oficial já validada é:", prompt)
        self.assertIn("6552701", prompt)


if __name__ == "__main__":
    unittest.main()
