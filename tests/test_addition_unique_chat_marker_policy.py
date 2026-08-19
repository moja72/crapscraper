from __future__ import annotations

import unittest

import app.addition_unique_chat_marker_policy as policy


class _MainLocator:
    def __init__(self, text: str):
        self.text = text

    def text_content(self, timeout=3000):
        return self.text

    def inner_text(self, timeout=3000):
        return self.text


class _Page:
    def __init__(self, text: str = "", evaluated=None):
        self.text = text
        self.evaluated = evaluated

    def locator(self, selector: str):
        if selector == "main":
            return _MainLocator(self.text)
        raise RuntimeError(selector)

    def evaluate(self, script, arg=None):
        if self.evaluated is not None:
            return self.evaluated
        return self.text


class AdditionUniqueChatMarkerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.old_desc = policy._ORIGINAL_DESCRIPTION_PROMPT
        self.old_img = policy._ORIGINAL_IMAGE_PROMPT
        policy._ORIGINAL_DESCRIPTION_PROMPT = lambda job: (
            "Pesquise o produto.\n\n"
            "Use como referência este exemplo longo que não deve ser capturado: "
            "Crie páginas profissionais com total liberdade visual. O exemplo explica recursos e benefícios "
            "de um produto diferente e existe apenas dentro do prompt para orientar tamanho e estrutura."
        )
        policy._ORIGINAL_IMAGE_PROMPT = lambda job: "Gere SOMENTE a imagem principal."

    def tearDown(self):
        policy._ORIGINAL_DESCRIPTION_PROMPT = self.old_desc
        policy._ORIGINAL_IMAGE_PROMPT = self.old_img

    def test_prompts_receive_distinct_unique_names(self):
        job = {"job_id": "add-6f3ec8d19128950e"}
        first = policy._description_prompt_named(job)
        second = policy._description_prompt_named(job)
        image = policy._image_prompt_named(job)
        self.assertIn("NOME INTERNO DESTA CONVERSA: CSADD-", first)
        self.assertRegex(first, r"CSADD-[A-Z0-9-]+-DESC-END")
        self.assertRegex(image, r"CSADD-[A-Z0-9-]+-IMG-END")
        self.assertNotEqual(first.splitlines()[0], second.splitlines()[0])

    def test_extracts_only_response_after_hidden_end_marker(self):
        description = (
            "Crie uma presença profissional para negócios de saúde e venda produtos online com o 123 Medicine. "
            "O tema combina estrutura voltada a sites médicos com integração ao WooCommerce, permitindo montar "
            "farmácias virtuais, lojas de produtos de saúde e páginas institucionais com layouts personalizáveis. "
            "É indicado para farmácias, clínicas, hospitais e outros projetos WordPress ligados à área da saúde."
        )
        main = (
            "NOME INTERNO DESTA CONVERSA: CSADD-ABC-120000-FFFF00-DESC\n"
            "texto do prompt\n"
            "Crie páginas profissionais com total liberdade visual e muitos outros detalhes do exemplo.\n"
            "CSADD-ABC-120000-FFFF00-DESC-END\n"
            "Pensou por 31s\n"
            f"{description}\n"
        )
        page = _Page(main)
        values = policy._visible_description_candidates(page)
        self.assertTrue(values)
        self.assertEqual(values[0], description)
        self.assertNotIn("liberdade visual", values[0])

    def test_text_after_last_marker_uses_latest_conversation_marker(self):
        text = (
            "CSADD-A-DESC-END resposta antiga\n"
            "CSADD-B-DESC-END resposta nova"
        )
        tail = policy._text_after_last_marker(text, policy._DESC_MARKER_RE)
        self.assertEqual(tail, "resposta nova")

    def test_image_candidates_after_marker_have_priority(self):
        page = _Page(evaluated=[{
            "src": "https://example.test/generated.png",
            "width": 1024,
            "height": 1024,
            "alt": "",
            "visible": True,
            "after": True,
        }])
        rows = policy._images_after_image_marker(page, {"https://example.test/reference.webp"})
        self.assertEqual(rows[0]["src"], "https://example.test/generated.png")


if __name__ == "__main__":
    unittest.main()
