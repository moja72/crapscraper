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

    def test_accepts_plain_commercial_description(self) -> None:
        description = (
            "Crie uma presença profissional para clínicas, hospitais, farmácias e outros serviços de saúde "
            "com um tema WordPress voltado ao segmento médico. O 123 Medicine ajuda a estruturar sites "
            "institucionais e comerciais para apresentar serviços, especialidades, informações e conteúdos "
            "de forma organizada, sendo uma opção versátil para projetos relacionados à saúde e atendimento."
        )
        self.assertEqual(policy._plausible_description(description), description)

    def test_selects_last_valid_candidate_and_ignores_sidebar_text(self) -> None:
        valid = (
            "Crie uma presença profissional para clínicas, hospitais, farmácias e outros serviços de saúde "
            "com um tema WordPress voltado ao segmento médico. O produto ajuda a organizar páginas e "
            "informações importantes para pacientes e clientes, oferecendo uma base visual adequada a "
            "projetos institucionais e comerciais ligados à área da saúde."
        )
        candidates = [
            {"text": "ChatGPT Plus", "source": "article"},
            {"text": "Novo chat em [CS] Automação", "source": "article"},
            {"text": valid, "source": "conversation-turn"},
        ]
        self.assertEqual(policy._select_description_candidate(candidates), valid)


if __name__ == "__main__":
    unittest.main()
