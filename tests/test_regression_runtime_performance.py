from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app import configuration
import app.comparison_runtime_performance as comparison_policy
import app.download_credit_fallback_policy as credit_policy
import app.operations.runtime as runtime
import app.update_operational_ui_policy as update_policy


class RuntimeRegressionTests(unittest.TestCase):
    def test_manual_monitor_variables_are_loaded_from_windows_user_environment(self) -> None:
        self.assertIn("SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED", configuration.WINDOWS_USER_ENVIRONMENT_KEYS)
        self.assertIn("SCRAPER_WORDPRESS_MANUAL_SECRET", configuration.WINDOWS_USER_ENVIRONMENT_KEYS)
        self.assertIn("SCRAPER_WORDPRESS_MANUAL_SECRET", configuration.SECRET_ENVIRONMENT_KEYS)

    def test_update_jobs_empty_poll_is_read_only(self) -> None:
        original_jobs = runtime._JOBS
        original_base = update_policy._BASE_MATERIALIZE
        try:
            runtime._JOBS = {}

            def should_not_materialize(*_args, **_kwargs):
                raise AssertionError("polling vazio não deve materializar/persistir runtime")

            update_policy._BASE_MATERIALIZE = should_not_materialize
            self.assertEqual(update_policy._read_update_jobs(()), [])
        finally:
            runtime._JOBS = original_jobs
            update_policy._BASE_MATERIALIZE = original_base

    def test_approximate_candidates_are_bounded_before_expensive_match(self) -> None:
        source_rows = [
            {
                "name_key": f"elementor addon {index}",
                "name_tokens": {"elementor", "addon", str(index)},
                "url_domain": "",
                "url_slug": "",
            }
            for index in range(500)
        ]
        site = {
            "name_key": "elementor addon target",
            "name_tokens": {"elementor", "addon", "target"},
            "url_domain": "",
            "url_slug": "",
        }
        captured: dict[str, int] = {}
        original_base = comparison_policy._BASE_BUILD_MATCH_CANDIDATES
        try:
            def fake_base(_site, _rows, **kwargs):
                captured["count"] = len(kwargs.get("candidate_source_indexes") or set())
                return []

            comparison_policy._BASE_BUILD_MATCH_CANDIDATES = fake_base
            with patch.dict(os.environ, {"SCRAPER_COMPARISON_MAX_APPROX_CANDIDATES": "80"}, clear=False):
                comparison_policy._bounded_build_match_candidates(
                    site,
                    source_rows,
                    candidate_source_indexes=set(range(500)),
                )
            self.assertEqual(captured.get("count"), 80)
        finally:
            comparison_policy._BASE_BUILD_MATCH_CANDIDATES = original_base

    def test_remote_credit_probe_is_opt_in(self) -> None:
        with patch.dict(os.environ, {"SCRAPER_DOWNLOAD_CREDITS_REMOTE_PROBE": ""}, clear=False):
            with patch.object(credit_policy, "_schedule_remote_refresh") as schedule:
                payload = credit_policy._patched_credit_snapshot(None)
        schedule.assert_not_called()
        self.assertFalse(payload["remote_probe_enabled"])
        self.assertFalse(payload["remote_refreshing"])


if __name__ == "__main__":
    unittest.main()
