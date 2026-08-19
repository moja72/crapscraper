from __future__ import annotations

import unittest

import app.addition_real_chat_url_policy as policy


class AdditionRealChatUrlPolicyTests(unittest.TestCase):
    def test_project_root_is_not_a_conversation(self) -> None:
        self.assertFalse(
            policy._is_real_conversation_url(
                "https://chatgpt.com/g/g-p-abc-cs-automacao/project"
            )
        )

    def test_real_project_conversation_is_accepted(self) -> None:
        self.assertTrue(
            policy._is_real_conversation_url(
                "https://chatgpt.com/g/g-p-abc-cs-automacao/c/6a85f533-4098-83e9-89c6-ea9d1865607c"
            )
        )

    def test_query_and_fragment_do_not_change_conversation_validity(self) -> None:
        self.assertTrue(
            policy._is_real_conversation_url(
                "https://chatgpt.com/g/g-p-abc-cs-automacao/c/6a85f533-4098-83e9-89c6-ea9d1865607c?foo=1#bar"
            )
        )

    def test_non_chatgpt_c_path_is_rejected(self) -> None:
        self.assertFalse(
            policy._is_real_conversation_url(
                "https://example.com/c/6a85f533-4098-83e9-89c6-ea9d1865607c"
            )
        )

    def test_prompt_fields_are_separated(self) -> None:
        field, label, _step = policy._field_for_prompt(
            "Pesquise e escreva SOMENTE a breve descrição comercial deste produto"
        )
        self.assertEqual(field, "description_chat_url")
        self.assertEqual(label, "Chat 1")

        field, label, _step = policy._field_for_prompt(
            "Gere SOMENTE a imagem principal deste produto"
        )
        self.assertEqual(field, "image_chat_url")
        self.assertEqual(label, "Chat 2")

    def test_labels_map_to_independent_fields(self) -> None:
        self.assertEqual(
            policy._field_for_label("Chat 1"),
            ("description_chat_url", "image_chat_url"),
        )
        self.assertEqual(
            policy._field_for_label("Chat 2"),
            ("image_chat_url", "description_chat_url"),
        )


if __name__ == "__main__":
    unittest.main()
