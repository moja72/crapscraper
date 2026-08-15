from __future__ import annotations

import unittest
from unittest.mock import patch

from app.app import ScraperApp
from app.resume_policy import install_resume_policy


class ResumePolicyTests(unittest.TestCase):
    def test_primary_start_uses_saved_continuation(self) -> None:
        install_resume_policy()
        app = object.__new__(ScraperApp)

        with patch.object(ScraperApp, "can_continue", return_value=True), \
                patch.object(ScraperApp, "get_continue_info", return_value={
                    "can_continue": True,
                    "run_mode": "full_sync",
                    "queue_index": 35,
                    "queue_total": 100,
                }), \
                patch("app.resume_policy._ORIGINAL_START", return_value={"ok": True}) as start:
            result = ScraperApp.start(
                app,
                run_mode="primary",
                run_payload={},
                resume=False,
                clear_logs=True,
            )

        self.assertTrue(result["ok"])
        kwargs = start.call_args.kwargs
        self.assertTrue(kwargs["resume"])
        self.assertTrue(kwargs["run_payload"]["resume"])
        self.assertEqual(kwargs["run_mode"], "full_sync")

    def test_explicit_other_mode_does_not_become_resume(self) -> None:
        install_resume_policy()
        app = object.__new__(ScraperApp)

        with patch.object(ScraperApp, "can_continue", return_value=True), \
                patch("app.resume_policy._ORIGINAL_START", return_value={"ok": True}) as start:
            ScraperApp.start(
                app,
                run_mode="categories_only",
                run_payload={},
                resume=False,
                clear_logs=True,
            )

        kwargs = start.call_args.kwargs
        self.assertFalse(kwargs["resume"])
        self.assertNotIn("resume", kwargs["run_payload"])


if __name__ == "__main__":
    unittest.main()
