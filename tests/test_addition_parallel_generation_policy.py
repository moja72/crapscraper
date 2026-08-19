from __future__ import annotations

import unittest

import app.addition_parallel_generation_policy as policy


class AdditionParallelGenerationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job = {
            "job_id": "add-test",
            "kind": "theme",
            "source_name": "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme",
            "source_version": "1.5.2",
            "source_product_url": (
                "https://www.ultrapackv2.com/item/"
                "themeforest-hospitais-clinicas-123-medicine-pharmacy-shop-hospital-medical-health-service-theme/"
            ),
            "source_official_url": "",
            "short_description": "",
            "image_path": "",
        }

    def test_parallel_image_prompt_never_exposes_ultrapack(self) -> None:
        prompt = policy._parallel_image_prompt(self.job)
        lowered = prompt.lower()
        self.assertNotIn("ultrapackv2.com", lowered)
        self.assertIn("themeforest", lowered)
        self.assertIn("não recuse", lowered)
        self.assertIn("não peça capturas", lowered)
        self.assertIn("fundo totalmente transparente", lowered)

    def test_parallel_image_prompt_treats_official_url_as_non_blocking_context(self) -> None:
        job = dict(self.job)
        job["source_official_url"] = (
            "https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701"
        )
        prompt = policy._parallel_image_prompt(job)
        self.assertIn("Página oficial já identificada:", prompt)
        self.assertIn("6552701", prompt)
        self.assertIn("A geração NÃO depende de conseguir abrir diretamente a página oficial", prompt)

    def test_known_refusal_message_is_recoverable_marker(self) -> None:
        response = (
            "Não consigo gerar esta imagem porque a página oficial exata que você forneceu "
            "não pôde ser acessada com sucesso, e seu pedido exige que a arte seja baseada nela. "
            "Se quiser, envie capturas da página oficial."
        ).lower()
        self.assertTrue(any(marker in response for marker in policy._IMAGE_REFUSAL_MARKERS))

    def test_fallback_prompt_does_not_require_direct_page_access(self) -> None:
        job = dict(self.job)
        job["source_official_url"] = (
            "https://themeforest.net/item/123medicine-ecommerce-wordpress-theme/6552701"
        )
        prompt = policy._fallback_image_prompt(job, has_official_capture=False).lower()
        self.assertIn("não tente condicionar a tarefa à abertura direta", prompt)
        self.assertIn("não recuse", prompt)
        self.assertIn("gere a imagem", prompt)

    def test_polling_budgets_match_operational_contract(self) -> None:
        self.assertEqual(policy._DESCRIPTION_TIMEOUT_SECONDS, 120)
        self.assertEqual(policy._IMAGE_TIMEOUT_SECONDS, 240)
        self.assertEqual(policy._DESCRIPTION_POLL_SECONDS, 15)
        self.assertEqual(policy._IMAGE_POLL_SECONDS, 30)


if __name__ == "__main__":
    unittest.main()
