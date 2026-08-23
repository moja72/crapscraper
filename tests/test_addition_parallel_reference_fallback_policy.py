from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.addition_parallel_reference_fallback_policy as policy


class AdditionParallelReferenceFallbackPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_base = policy._BASE_RUN_TWO_CHATS

    def tearDown(self) -> None:
        policy._BASE_RUN_TWO_CHATS = self.previous_base

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


if __name__ == "__main__":
    unittest.main()
