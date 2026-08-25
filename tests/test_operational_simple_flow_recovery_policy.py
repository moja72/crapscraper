from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.operational_simple_flow_recovery_policy as policy


class OperationalSimpleFlowRecoveryPolicyTests(unittest.TestCase):
    def tearDown(self) -> None:
        policy._BASE_PREPARE_UPDATE = None
        policy._BASE_EXECUTE_UPDATE_ONE = None

    def test_validation_reason_surfaces_real_source_failure(self) -> None:
        preview = {
            "ready": False,
            "validations": [
                {"key": "product", "ok": True, "detail": "Woo #1"},
                {
                    "key": "ultrapack",
                    "ok": False,
                    "level": "error",
                    "detail": "Falha no download Ultrapack: HTTP 401",
                },
                {
                    "key": "downloaded",
                    "ok": False,
                    "level": "error",
                    "detail": "Download bloqueado pela validação",
                },
            ],
        }
        self.assertEqual(
            policy._validation_reason(preview),
            "Falha no download Ultrapack: HTTP 401",
        )

    def test_recoverable_failures_cover_auth_and_missing_local_file(self) -> None:
        self.assertTrue(policy._is_auth_failure("Falha no download Ultrapack: HTTP 401"))
        self.assertTrue(
            policy._is_auth_failure(
                "Botao real de download nao encontrado no produto autenticado"
            )
        )
        self.assertTrue(policy._is_transient_local_failure("[Errno 2] No such file"))
        self.assertFalse(policy._is_auth_failure("fonte anterior à comparação"))

    def test_prepare_retries_once_after_auth_failure_and_discards_cached_session(self) -> None:
        closed = []
        session = SimpleNamespace(close=lambda: closed.append(True))
        primary = SimpleNamespace(ultrapack_http_session=session)
        job = SimpleNamespace(
            job_id="job-1",
            ultrapack_url="https://www.ultrapackv2.com/item/plugin/",
            execution_error="",
        )
        logger = SimpleNamespace(log=Mock())
        base = Mock(
            side_effect=[
                RuntimeError("A preparação terminou sem liberar o produto para atualização."),
                ({"ready": True}, {"ready": True}),
            ]
        )
        policy._BASE_PREPARE_UPDATE = base

        blocked_preview = {
            "ready": False,
            "validations": [
                {
                    "key": "ultrapack",
                    "ok": False,
                    "level": "error",
                    "detail": "Falha no download Ultrapack: HTTP 401",
                }
            ],
        }

        with patch.object(policy.runtime, "get_preview", return_value=blocked_preview), patch.object(
            policy.web, "_get_primary_app", return_value=primary
        ):
            result = policy._patched_prepare_update(job, object(), logger)

        self.assertEqual(result[0]["ready"], True)
        self.assertEqual(base.call_count, 2)
        self.assertIsNone(primary.ultrapack_http_session)
        self.assertEqual(closed, [True])

    def test_prepare_does_not_retry_nonrecoverable_validation(self) -> None:
        job = SimpleNamespace(job_id="job-2", ultrapack_url="", execution_error="")
        logger = SimpleNamespace(log=Mock())
        base = Mock(
            side_effect=RuntimeError(
                "A preparação terminou sem liberar o produto para atualização."
            )
        )
        policy._BASE_PREPARE_UPDATE = base
        blocked_preview = {
            "ready": False,
            "validations": [
                {
                    "key": "version",
                    "ok": False,
                    "level": "error",
                    "detail": "fonte anterior à comparação",
                }
            ],
        }

        with patch.object(policy.runtime, "get_preview", return_value=blocked_preview):
            with self.assertRaisesRegex(
                RuntimeError, "Preparação bloqueada: fonte anterior à comparação"
            ):
                policy._patched_prepare_update(job, object(), logger)

        self.assertEqual(base.call_count, 1)

    def test_prepare_retries_once_after_errno_2(self) -> None:
        job = SimpleNamespace(job_id="job-3", ultrapack_url="", execution_error="")
        logger = SimpleNamespace(log=Mock())
        base = Mock(
            side_effect=[
                FileNotFoundError(2, "No such file"),
                ({"ready": True}, {"ready": True}),
            ]
        )
        policy._BASE_PREPARE_UPDATE = base
        with patch.object(policy.runtime, "get_preview", side_effect=KeyError("no preview")):
            result = policy._patched_prepare_update(job, object(), logger)
        self.assertTrue(result[0]["ready"])
        self.assertEqual(base.call_count, 2)

    def test_wrong_owner_is_reported_as_safe_server_metadata_block(self) -> None:
        policy._BASE_EXECUTE_UPDATE_ONE = Mock(
            side_effect=RuntimeError(
                "Helper remoto retornou falha: wrong owner for 301-redirects-pro.zip"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "owner=plugi2090"):
            policy._patched_execute_update_one("job-4", object())

    def test_candidate_paths_ignore_disappearing_files_and_keep_existing_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stable = root / "stable.zip"
            stable.write_bytes(b"zip")
            missing = root / "missing.zip"

            original_glob = Path.glob

            def fake_glob(path: Path, pattern: str):
                if path == root and pattern == "*.zip":
                    return iter((missing, stable))
                return original_glob(path, pattern)

            with patch.object(Path, "glob", fake_glob):
                paths = policy._patched_candidate_paths(root, "")

            self.assertEqual(paths, [stable])


if __name__ == "__main__":
    unittest.main()
