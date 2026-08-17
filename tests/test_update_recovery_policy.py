from __future__ import annotations

import unittest
from unittest.mock import patch

import app.update_recovery_policy as policy


class UpdateRecoveryPolicyTests(unittest.TestCase):
    def test_recovery_ui_does_not_rerender_unchanged_data_or_interrupt_actions(self) -> None:
        script = policy._SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("recoverySignature", script)
        self.assertIn("panel.dataset.recoverySignature === signature", script)
        self.assertIn("updateRecoveryBusy", script)
        self.assertIn("if (meta.innerHTML !== metaHtml)", script)

    def test_recovery_script_is_injected_before_body_close(self) -> None:
        with patch.object(
            policy,
            "_ORIGINAL_RENDER_PANEL_PAGE",
            return_value="<html><body><main>Painel</main></body></html>",
        ):
            html = policy._patched_render_panel_page()

        self.assertIn("data-update-recovery-ui", html)
        self.assertIn("Reprocessar recuperáveis", html)
        self.assertLess(html.index("data-update-recovery-ui"), html.index("</body>"))

    def test_missing_script_does_not_break_panel(self) -> None:
        with patch.object(policy, "_SCRIPT_PATH", policy._SCRIPT_PATH.with_name("missing.js")), patch.object(
            policy,
            "_ORIGINAL_RENDER_PANEL_PAGE",
            return_value="<html><body>Painel</body></html>",
        ):
            html = policy._patched_render_panel_page()

        self.assertEqual(html, "<html><body>Painel</body></html>")


if __name__ == "__main__":
    unittest.main()
