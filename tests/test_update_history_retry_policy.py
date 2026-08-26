from __future__ import annotations

import unittest
from pathlib import Path

import app.update_history_retry_policy as policy


class UpdateHistoryRetryPolicyTests(unittest.TestCase):
    def test_script_reuses_safe_simple_update_flow(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "app" / "static" / "update_history_retry.js").read_text(encoding="utf-8")

        self.assertIn("Tentar novamente", script)
        self.assertIn('request("/operacoes/simples/atualizar"', script)
        self.assertIn('request("/operacoes/simples/status")', script)
        self.assertIn('JSON.stringify({job_id: jobId})', script)

    def test_success_reloads_history_and_switches_to_completed(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "app" / "static" / "update_history_retry.js").read_text(encoding="utf-8")

        self.assertIn('shared.load("update", true)', script)
        self.assertIn("[data-oh-mode='completed']", script)
        self.assertIn("await reloadHistory(true)", script)

    def test_retry_button_is_limited_to_visible_update_error_rows(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "app" / "static" / "update_history_retry.js").read_text(encoding="utf-8")

        self.assertIn('const ROOT = "#updates_history_accordion"', script)
        self.assertIn('const ERROR_MODE = \'[data-oh-mode="errors"].is-active\'', script)
        self.assertIn("if (!errorsVisible)", script)

    def test_policy_injects_final_retry_script(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda *args, **kwargs: "<html><body>ok</body></html>"
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original

        self.assertIn("data-update-history-retry", html)
        self.assertIn("/operacoes/simples/atualizar", html)


if __name__ == "__main__":
    unittest.main()
