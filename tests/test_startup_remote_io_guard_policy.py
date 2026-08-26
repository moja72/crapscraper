from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app.startup_remote_io_guard_policy as policy


class _FakeThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return self.started


class StartupRemoteIoGuardPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_repair = policy._BASE_REPAIR
        self.thread = policy._REPAIR_THREAD
        self.last_result = dict(policy._LAST_RESULT)

    def tearDown(self) -> None:
        policy._BASE_REPAIR = self.base_repair
        policy._REPAIR_THREAD = self.thread
        policy._LAST_RESULT.clear()
        policy._LAST_RESULT.update(self.last_result)

    def test_sync_path_schedules_repair_without_calling_remote_io_inline(self) -> None:
        remote = Mock(side_effect=AssertionError("WooCommerce não deve rodar na pilha do startup"))
        policy._BASE_REPAIR = remote
        policy._REPAIR_THREAD = None
        policy._LAST_RESULT.clear()
        policy._LAST_RESULT.update(scheduled=False, running=False, completed=False, error="")
        fake = _FakeThread()

        with patch.object(policy.threading, "Thread", return_value=fake):
            result = policy._deferred_repair_existing_additions()

        remote.assert_not_called()
        self.assertTrue(fake.started)
        self.assertTrue(result["scheduled"])
        self.assertFalse(result["running"])

    def test_background_worker_runs_original_repair_and_records_result(self) -> None:
        policy._BASE_REPAIR = Mock(return_value={
            "checked": 3,
            "repaired_products": 1,
            "repaired_variations": 2,
            "errors": [],
        })
        policy._REPAIR_THREAD = _FakeThread()
        policy._LAST_RESULT.clear()
        policy._LAST_RESULT.update(scheduled=True, running=False, completed=False, error="")

        policy._run_repair_after_startup(0)

        policy._BASE_REPAIR.assert_called_once_with()
        self.assertTrue(policy._LAST_RESULT["completed"])
        self.assertFalse(policy._LAST_RESULT["running"])
        self.assertEqual(policy._LAST_RESULT["checked"], 3)
        self.assertEqual(policy._LAST_RESULT["repaired_variations"], 2)

    def test_guard_is_installed_before_main_policy_install_sequence(self) -> None:
        root = Path(__file__).resolve().parents[1]
        process_source = (root / "app" / "process_modal_stability_policy.py").read_text(encoding="utf-8")
        main_source = (root / "main.py").read_text(encoding="utf-8")

        self.assertIn("install_startup_remote_io_guard_policy()", process_source)
        import_pos = main_source.index("from app.process_modal_stability_policy import")
        install_pos = main_source.index("install_resume_policy()")
        self.assertLess(import_pos, install_pos)


if __name__ == "__main__":
    unittest.main()
