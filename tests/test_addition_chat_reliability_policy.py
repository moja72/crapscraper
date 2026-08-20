from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_chat_reliability_policy as policy


class _Page:
    def __init__(self, url: str) -> None:
        self.url = url


class AdditionChatReliabilityPolicyTests(unittest.TestCase):
    def test_desired_titles_use_colon_format(self) -> None:
        job = {"source_name": "Presto Player Pro"}
        with patch.object(policy.additions, "_row", return_value=job):
            self.assertEqual(policy._desired_title("job", "Chat 1"), "Descrição: Presto Player Pro")
            self.assertEqual(policy._desired_title("job", "Chat 2"), "Imagem: Presto Player Pro")

    def test_conversation_id_is_extracted_from_real_chat_url(self) -> None:
        page = _Page("https://chatgpt.com/g/g-p-projeto/c/6a860d53-9dc8-83e9-931d-9e2599890abf")
        self.assertEqual(policy._conversation_id(page), "6a860d53-9dc8-83e9-931d-9e2599890abf")

    def test_portuguese_rate_limit_warning_is_detected(self) -> None:
        text = (
            "Excesso de solicitações. Você está fazendo solicitações rápido demais. "
            "Limitamos temporariamente o acesso às suas conversas para proteger seus dados."
        )
        with patch.object(policy, "_body_text", return_value=text):
            self.assertTrue(policy._rate_limit_visible(object()))

    def test_normal_page_is_not_classified_as_rate_limit(self) -> None:
        with patch.object(policy, "_body_text", return_value="Descrição pronta para o produto"):
            self.assertFalse(policy._rate_limit_visible(object()))


if __name__ == "__main__":
    unittest.main()
