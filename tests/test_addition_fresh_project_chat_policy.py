from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_fresh_project_chat_policy as policy


class FakePage:
    def __init__(self, url: str, turns: int = 0) -> None:
        self.url = url
        self.turns = turns

    def evaluate(self, _script: str):
        return self.turns


class AdditionFreshProjectChatPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = "https://chatgpt.com/g/g-p-abc-cs-automacao/project"

    def test_canonical_project_url_prefers_project_landing(self) -> None:
        self.assertEqual(
            policy._canonical_project_url(
                "https://chatgpt.com/g/g-p-abc-cs-automacao/c/123"
            ),
            self.project,
        )

    def test_route_candidates_keep_legacy_root_only_as_fallback(self) -> None:
        self.assertEqual(
            policy._project_route_candidates(self.project),
            [
                self.project,
                "https://chatgpt.com/g/g-p-abc-cs-automacao",
            ],
        )

    def test_same_project_requires_matching_token_and_chatgpt_host(self) -> None:
        self.assertTrue(
            policy._same_project(
                self.project,
                "https://chatgpt.com/g/g-p-abc-cs-automacao/c/123",
            )
        )
        self.assertFalse(
            policy._same_project(
                self.project,
                "https://chatgpt.com/g/g-p-other/project",
            )
        )
        self.assertFalse(
            policy._same_project(
                self.project,
                "https://example.com/g/g-p-abc-cs-automacao/project",
            )
        )

    def test_blank_project_chat_accepts_zero_turn_project_landing(self) -> None:
        page = FakePage(self.project, turns=0)
        with patch.object(policy.one_click, "_composer", return_value=object()):
            self.assertTrue(policy._blank_project_chat(page, self.project))

    def test_blank_project_chat_rejects_existing_conversation_turn(self) -> None:
        page = FakePage(self.project, turns=1)
        with patch.object(policy.one_click, "_composer", return_value=object()):
            self.assertFalse(policy._blank_project_chat(page, self.project))

    def test_blank_project_chat_rejects_unknown_conversation_structure(self) -> None:
        page = FakePage(self.project, turns=-1)
        with patch.object(policy.one_click, "_composer", return_value=object()):
            self.assertFalse(policy._blank_project_chat(page, self.project))

    def test_blank_project_chat_rejects_reopened_same_conversation(self) -> None:
        existing = "https://chatgpt.com/g/g-p-abc-cs-automacao/c/123"
        page = FakePage(existing, turns=0)
        with patch.object(policy.one_click, "_composer", return_value=object()):
            self.assertFalse(
                policy._blank_project_chat(page, self.project, before_url=existing)
            )


if __name__ == "__main__":
    unittest.main()
