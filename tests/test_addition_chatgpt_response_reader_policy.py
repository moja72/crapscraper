from __future__ import annotations

import unittest

import app.addition_chatgpt_response_reader_policy as policy


class AdditionChatGPTResponseReaderPolicyTests(unittest.TestCase):
    def test_rejects_original_user_prompt(self) -> None:
        prompt = """Escreva SOMENTE a breve descrição comercial deste produto para o e-commerce PluginTema.

REGRAS OBRIGATÓRIAS
- Faça aproximadamente 400 a 500 caracteres.

Retorne SOMENTE a descrição final."""
        self.assertEqual(policy._plausible_description(prompt), "")

    def test_rejects_refined_user_prompt(self) -> None:
        prompt = """Gere apenas a breve descrição comercial deste produto para o e-commerce PluginTema.

OBJETIVO DA DESCRIÇÃO
Escreva um único parágrafo em português do Brasil.

Retorne SOMENTE o parágrafo final da breve descrição."""
        self.assertEqual(policy._plausible_description(prompt), "")

    def test_accepts_plain_commercial_description(self) -> None:
        description = (
            "Apresente serviços de saúde com um site profissional e organizado. O 123 Medicine é um tema WordPress "
            "voltado a clínicas, hospitais, farmácias e negócios da área médica, ajudando a estruturar páginas para "
            "serviços, especialidades, equipe e informações institucionais com uma comunicação visual adequada ao "
            "segmento. Assim, o projeto ganha uma base clara para apresentar conteúdos a pacientes e clientes."
        )
        self.assertEqual(policy._plausible_description(description), description)

    def test_prefers_conversation_turn_over_generic_markdown(self) -> None:
        valid = (
            "Apresente serviços de saúde com um site profissional e organizado. O 123 Medicine ajuda clínicas, "
            "hospitais e farmácias a estruturar páginas para serviços, especialidades, equipe e informações "
            "institucionais, reunindo conteúdos importantes em uma apresentação clara e adequada ao segmento médico."
        )
        other = (
            "Este é apenas um texto genérico bastante longo usado para simular outro bloco visível na interface do "
            "navegador e não deve vencer um turno real da conversa quando ambos aparecem como candidatos válidos. "
            "Ele existe somente para validar a prioridade de seleção do detector de resposta."
        )
        candidates = [
            {"text": other, "source": "markdown"},
            {"text": valid, "source": "conversation-turn"},
        ]
        self.assertEqual(policy._select_description_candidate(candidates), valid)

    def test_refined_prompt_requests_only_description(self) -> None:
        prompt = policy._description_prompt_refined(
            {
                "kind": "theme",
                "source_name": "123 Medicine",
                "source_version": "1.5.2",
                "source_product_url": "https://example.test/source",
                "source_official_url": "https://example.test/official",
            }
        )
        lowered = prompt.lower()
        self.assertIn("gere apenas a breve descrição comercial", lowered)
        self.assertIn("400 a 500 caracteres", lowered)
        self.assertIn("retorne somente o parágrafo final", lowered)
        self.assertIn("não use título", lowered)
        self.assertIn("meta description", lowered)
        self.assertIn("não escreva rótulos", lowered)
        self.assertNotIn("título seo:", lowered)
        self.assertNotIn("tags relevantes:", lowered)


if __name__ == "__main__":
    unittest.main()
