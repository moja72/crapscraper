from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.addition_parallel_reference_fallback_policy as policy


class AdditionParallelReferenceFallbackPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_base = policy._BASE_RUN_TWO_CHATS
        self.previous_image_prompt = policy._BASE_IMAGE_PROMPT

    def tearDown(self) -> None:
        policy._BASE_RUN_TWO_CHATS = self.previous_base
        policy._BASE_IMAGE_PROMPT = self.previous_image_prompt

    def test_missing_reference_skips_parallel_and_uses_safe_fallback(self) -> None:
        calls: list[str] = []

        def parallel(job_id: str):
            calls.append(f"parallel:{job_id}")
            raise AssertionError("O fluxo paralelo não deveria ser chamado sem referência local.")

        def fallback(job_id: str):
            calls.append(f"fallback:{job_id}")
            return {"job_id": job_id, "ok": True}

        policy._BASE_RUN_TWO_CHATS = parallel
        missing = Path("missing/exemplo tema.webp")

        with patch.object(policy, "_reference_for_job", return_value=missing), \
             patch.object(policy.capture, "_ORIGINAL_RUN_TWO_CHATS", fallback), \
             patch.object(policy.one_click, "_emit", return_value=None):
            result = policy._run_with_optional_reference("add-test")

        self.assertEqual(result["job_id"], "add-test")
        self.assertEqual(calls, ["fallback:add-test"])

    def test_attachment_failure_falls_back_without_exposing_old_error(self) -> None:
        calls: list[str] = []

        def parallel(job_id: str):
            calls.append(f"parallel:{job_id}")
            raise RuntimeError("Não foi possível anexar a referência visual obrigatória exemplo tema.webp.")

        def fallback(job_id: str):
            calls.append(f"fallback:{job_id}")
            return {"job_id": job_id, "ok": True}

        policy._BASE_RUN_TWO_CHATS = parallel

        with patch.object(policy, "_reference_for_job", return_value=Path(__file__)), \
             patch.object(policy.capture, "_ORIGINAL_RUN_TWO_CHATS", fallback), \
             patch.object(policy.one_click, "_emit", return_value=None):
            result = policy._run_with_optional_reference("add-test")

        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["parallel:add-test", "fallback:add-test"])

    def test_unrelated_parallel_error_is_not_hidden(self) -> None:
        def parallel(_job_id: str):
            raise RuntimeError("Falha real do ChatGPT")

        policy._BASE_RUN_TWO_CHATS = parallel

        with patch.object(policy, "_reference_for_job", return_value=Path(__file__)), \
             patch.object(policy.one_click, "_emit", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Falha real do ChatGPT"):
                policy._run_with_optional_reference("add-test")

    def test_old_one_argument_prompt_accepts_reference_attached_contract(self) -> None:
        calls: list[str] = []

        def old_prompt(job):
            calls.append(str(job.get("source_name") or ""))
            return (
                "Imagem: Example Theme\n\n"
                "Use o arquivo anexado apenas como referência de mockup. "
                "Gere uma NOVA imagem 1:1 com fundo transparente."
            )

        policy._BASE_IMAGE_PROMPT = old_prompt
        prompt = policy._image_prompt_with_optional_reference(
            {"source_name": "Example Theme", "kind": "theme"},
            reference_attached=False,
        )

        self.assertEqual(calls, ["Example Theme"])
        self.assertIn("Não há mockup local anexado", prompt)
        self.assertNotIn("Use o arquivo anexado apenas", prompt)

    def test_new_prompt_receives_reference_flag_normally(self) -> None:
        flags: list[bool] = []

        def new_prompt(job, *, reference_attached: bool):
            flags.append(reference_attached)
            return f"{job.get('source_name')}:{reference_attached}"

        policy._BASE_IMAGE_PROMPT = new_prompt
        prompt = policy._image_prompt_with_optional_reference(
            {"source_name": "Example Plugin", "kind": "plugin"},
            reference_attached=False,
        )

        self.assertEqual(flags, [False])
        self.assertEqual(prompt, "Example Plugin:False")


if __name__ == "__main__":
    unittest.main()
