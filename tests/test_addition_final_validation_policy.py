from __future__ import annotations

import unittest

import app.addition_final_validation_policy as policy


class AdditionFinalValidationPolicyTests(unittest.TestCase):
    def test_rejects_chatgpt_interface_script_as_description(self) -> None:
        script = (
            "(function Abe(e,t){e?.addEventListener(`input`,()=>{performance.mark(t)},{once:!0})})"
            "(document.currentScript?.parentElement,\"composer.first-prompt-input\");"
            "window.oai_logHTML?window.oai_logHTML():window.oai_SSR_HTML=window.oai_SSR_HTML||Date.now();"
            "requestAnimationFrame((function(){window.oai_logTTI?window.oai_logTTI():window.oai_SSR_TTI=Date.now()}))"
        )
        self.assertEqual(policy._validated_description(script), "")

    def test_accepts_real_commercial_description(self) -> None:
        description = (
            "Organize serviços de saúde e produtos farmacêuticos em um site claro e profissional. "
            "O 123 Medicine é um tema WordPress voltado a farmácias, clínicas, hospitais e serviços médicos, "
            "ajudando a apresentar atendimentos, especialidades, equipe, informações institucionais e itens da loja. "
            "Assim, o projeto reúne conteúdo e área comercial em uma estrutura adequada ao segmento de saúde."
        )
        self.assertEqual(policy._validated_description(description), description)

    def test_description_prompt_uses_product_pages_as_primary_context(self) -> None:
        prompt = policy._description_prompt(
            {
                "kind": "theme",
                "source_name": "123 Medicine",
                "source_version": "1.5.2",
                "source_product_url": "https://example.test/source",
                "source_official_url": "https://example.test/official",
            }
        ).lower()
        self.assertIn("fonte principal de contexto", prompt)
        self.assertIn("consulte e analise as páginas", prompt)
        self.assertIn("400 a 500 caracteres", prompt)
        self.assertIn("retorne somente o parágrafo final", prompt)
        self.assertNotIn("título seo:", prompt)
        self.assertNotIn("tags:", prompt)

    def test_theme_image_prompt_uses_reference_only_as_mockup(self) -> None:
        prompt = policy._image_prompt(
            {
                "kind": "theme",
                "source_name": "123 Medicine",
                "source_product_url": "https://example.test/source",
                "source_official_url": "https://example.test/official",
            }
        ).lower()
        self.assertIn("exemplo tema.webp", prompt)
        self.assertIn("somente como referência de composição", prompt)
        self.assertIn("não copie a marca", prompt)
        self.assertIn("tema real do produto atual", prompt)
        self.assertIn("monitor apple", prompt)
        self.assertIn("fundo totalmente transparente", prompt)
        self.assertIn("consulte e analise as páginas", prompt)

    def test_plugin_image_prompt_requires_real_identity_and_box(self) -> None:
        prompt = policy._image_prompt(
            {
                "kind": "plugin",
                "source_name": "Plugin Example",
                "source_product_url": "https://example.test/source",
                "source_official_url": "https://example.test/official",
            }
        ).lower()
        self.assertIn("exemplo plugin.webp", prompt)
        self.assertIn("3 faces/lados", prompt)
        self.assertIn("identidade real do plugin", prompt)
        self.assertIn("vitalício | ilimitado | atualizado", prompt)

    def test_image_candidate_rejects_user_turn(self) -> None:
        self.assertLess(
            policy._candidate_score(
                {
                    "role": "user",
                    "text": "Agora gere SOMENTE a imagem principal deste produto.",
                }
            ),
            0,
        )
        self.assertGreater(
            policy._candidate_score({"role": "assistant", "text": "Worked for 2m"}),
            0,
        )

    def test_remote_missing_recognizes_404_only(self) -> None:
        self.assertTrue(policy._remote_product_missing(RuntimeError("HTTP 404 not found")))
        self.assertFalse(policy._remote_product_missing(RuntimeError("timeout connecting to WooCommerce")))


if __name__ == "__main__":
    unittest.main()
