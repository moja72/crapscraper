from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.startup_fast_path_policy as policy


class StartupFastPathPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.startup_phase = policy._STARTUP_PHASE
        self.base_load = policy._BASE_LOAD_INITIAL_SUMMARY
        self.base_render = policy._BASE_RENDER

    def tearDown(self) -> None:
        policy._STARTUP_PHASE = self.startup_phase
        policy._BASE_LOAD_INITIAL_SUMMARY = self.base_load
        policy._BASE_RENDER = self.base_render

    def test_startup_summary_uses_memory_without_calling_heavy_loader(self) -> None:
        heavy = Mock(side_effect=AssertionError("heavy loader não deve rodar no boot"))
        policy._BASE_LOAD_INITIAL_SUMMARY = heavy
        policy._STARTUP_PHASE = True
        app = SimpleNamespace(snapshot=lambda max_logs=0: {"loaded": False, "max_logs": max_logs})

        result = policy._fast_load_initial_summary(app)

        self.assertEqual(result, {"loaded": False, "max_logs": 0})
        heavy.assert_not_called()

    def test_after_socket_creation_normal_summary_loader_is_restored(self) -> None:
        heavy = Mock(return_value={"loaded": True})
        policy._BASE_LOAD_INITIAL_SUMMARY = heavy
        policy._STARTUP_PHASE = False
        app = SimpleNamespace()

        result = policy._fast_load_initial_summary(app)

        self.assertEqual(result, {"loaded": True})
        heavy.assert_called_once_with(app)

    def test_prepare_app_refreshes_only_active_context_and_never_loads_summary(self) -> None:
        refresh = Mock()
        load_summary = Mock()
        primary = SimpleNamespace(
            refresh_slots_state=refresh,
            load_initial_summary=load_summary,
        )
        manager = object()
        target = object()

        with (
            patch.object(policy.web, "_ensure_manager", return_value=manager),
            patch.object(policy.web, "_get_primary_app", return_value=primary),
        ):
            result = policy._fast_prepare_app(target)

        self.assertIs(result, target)
        refresh.assert_called_once_with()
        load_summary.assert_not_called()

    def test_final_html_removes_eager_process_network_polling(self) -> None:
        policy._BASE_RENDER = lambda *args, **kwargs: policy._PROCESS_HISTORY_START_FINAL_SAFE

        html = policy._patched_render_panel_page()

        self.assertIn('$("#cs_processes_button")?.addEventListener', html)
        self.assertIn("if (processMonitorVisible()) pollCredits()", html)
        self.assertNotIn("window.setTimeout(pollBackendHistory, 1400)", html)
        self.assertNotIn("window.setInterval(pollBackendHistory, 2600)", html)


if __name__ == "__main__":
    unittest.main()
