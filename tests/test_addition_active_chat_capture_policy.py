from __future__ import annotations

import unittest

import app.addition_active_chat_capture_policy as policy


class _FakePage:
    def __init__(self, evaluated=None):
        self.evaluated = evaluated
        self.front_calls = 0

    def bring_to_front(self):
        self.front_calls += 1

    def wait_for_timeout(self, _ms):
        return None

    def evaluate(self, _script, _arg=None):
        return self.evaluated


class AdditionActiveChatCapturePolicyTests(unittest.TestCase):
    def test_direct_description_reads_final_paragraph_from_active_chat(self):
        description = (
            "Crie uma presença profissional para negócios da área da saúde com o 123 Medicine, um tema WordPress "
            "voltado a farmácias, hospitais, clínicas e serviços médicos. Ele ajuda a organizar produtos, serviços "
            "e informações institucionais em um site alinhado ao segmento de saúde. É indicado para farmácias online, "
            "centros médicos, consultórios e outros projetos de saúde."
        )
        page = _FakePage({
            "blocks": [
                {"text": "IDENTIFICADOR INTERNO: CSADD-TEST-DESC", "order": 0},
                {"text": description, "order": 1},
            ],
            "mainText": description,
        })
        values = policy._direct_description_candidates(page)
        self.assertTrue(values)
        self.assertEqual(values[0], description)
        self.assertGreaterEqual(page.front_calls, 1)

    def test_direct_description_rejects_prompt_example(self):
        example = (
            "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
            "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress. "
            "Ele funciona com widgets premium, templates e construtores para tema, formulários e pop-ups."
        )
        page = _FakePage({"blocks": [{"text": example, "order": 0}], "mainText": example})
        self.assertEqual(policy._direct_description_candidates(page), [])

    def test_direct_new_image_ignores_reference_already_present(self):
        page = _FakePage([
            {
                "index": 0,
                "src": "https://example.test/generated.png",
                "width": 1024,
                "height": 1024,
                "visible": True,
                "alt": "",
            }
        ])
        rows = policy._direct_new_images(page, {"https://example.test/reference.webp"})
        self.assertEqual(rows[0]["src"], "https://example.test/generated.png")
        self.assertGreaterEqual(page.front_calls, 1)

    def test_prompt_markers_are_not_accepted_as_description(self):
        text = "IDENTIFICADOR INTERNO: CSADD-ABC-DESC Pesquise e escreva SOMENTE a breve descrição comercial deste produto."
        self.assertTrue(policy._looks_like_prompt(text))


if __name__ == "__main__":
    unittest.main()
