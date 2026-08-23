from __future__ import annotations

import unittest

import app.addition_image_prompt_autosend_policy as policy


class AdditionImagePromptAutosendPolicyTests(unittest.TestCase):
    def test_plugin_prompt_uses_project_reference(self) -> None:
        prompt = policy._project_reference_image_prompt(
            {
                "kind": "plugin",
                "source_name": "Example Plugin",
                "source_product_url": "https://codecanyon.net/item/example/123",
            }
        )
        self.assertIn("Exemplo Plugin.webp", prompt)
        self.assertIn("arquivos deste Projeto do ChatGPT", prompt)
        self.assertIn("Não peça para o usuário anexar", prompt)
        self.assertIn("Vitalício | Ilimitado | Atualizado", prompt)
        self.assertNotIn("Use o arquivo anexado", prompt)

    def test_theme_prompt_uses_project_reference(self) -> None:
        prompt = policy._project_reference_image_prompt(
            {
                "kind": "theme",
                "source_name": "Example Theme",
                "source_product_url": "https://themeforest.net/item/example/123",
            }
        )
        self.assertIn("Exemplo Tema.webp", prompt)
        self.assertIn("arquivos deste Projeto do ChatGPT", prompt)
        self.assertIn("monitor Apple", prompt)
        self.assertIn("celular", prompt)
        self.assertNotIn("Use o arquivo anexado", prompt)

    def test_mapped_chat_reprompt_window_is_short(self) -> None:
        self.assertLessEqual(policy._MAPPED_CHAT_REPROMPT_SECONDS, 2)

    def test_image_prompt_is_detected(self) -> None:
        prompt = policy._project_reference_image_prompt(
            {"kind": "plugin", "source_name": "Example Plugin"}
        )
        self.assertTrue(policy._is_image_prompt(prompt))


if __name__ == "__main__":
    unittest.main()
