from __future__ import annotations

import unittest

import app.addition_chat_binding_policy as policy


class AdditionChatBindingPolicyTests(unittest.TestCase):
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
            "short_description": "",
        }

    def test_description_prompt_returns_only_description(self) -> None:
        prompt = policy._description_only_prompt(self.job)
        lowered = prompt.lower()
        self.assertIn("responda somente com o parágrafo final da descrição", lowered)
        self.assertNotIn("pagina_oficial:", lowered)
        self.assertNotIn("titulo_oficial:", lowered)
        self.assertNotIn("descricao:", lowered)
        self.assertNotIn("ultrapackv2.com", lowered)

    def test_description_prompt_keeps_marketplace_context(self) -> None:
        prompt = policy._description_only_prompt(self.job).lower()
        self.assertIn("themeforest", prompt)
        self.assertIn("pesquisa", prompt)
        self.assertIn("produto exato", prompt)

    def test_chat_url_comparison_ignores_query_and_fragment(self) -> None:
        left = "https://chatgpt.com/g/project/c/abc123?foo=1#bottom"
        right = "https://chatgpt.com/g/project/c/abc123"
        self.assertTrue(policy._same_chat_url(left, right))

    def test_chat_url_comparison_rejects_different_conversations(self) -> None:
        self.assertFalse(
            policy._same_chat_url(
                "https://chatgpt.com/g/project/c/description-chat",
                "https://chatgpt.com/g/project/c/image-chat",
            )
        )

    def test_existing_description_does_not_require_official_url(self) -> None:
        job = dict(self.job)
        job["short_description"] = (
            "Organize serviços de saúde em um site claro e profissional. O 123 Medicine oferece uma estrutura WordPress "
            "voltada a farmácias, clínicas, hospitais e projetos médicos, ajudando a apresentar serviços, equipe, produtos "
            "e informações institucionais de forma organizada. É indicado para negócios de saúde que precisam reunir conteúdo "
            "e atendimento em uma experiência consistente."
        )
        self.assertTrue(policy._valid_existing_description(job))


if __name__ == "__main__":
    unittest.main()
