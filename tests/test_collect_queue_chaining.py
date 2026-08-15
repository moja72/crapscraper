from __future__ import annotations

import unittest
from unittest.mock import patch

from app.app import ScraperRunManager
from app.models import build_context


class CollectQueueChainingTests(unittest.TestCase):
    def test_enabled_rule_starts_target_after_exact_source_finishes(self) -> None:
        source = {
            "slot_name": "default",
            "site_key": "plugintheme",
            "item_type_key": "plugin_theme",
            "account_key": "coproducaolancamentos",
        }
        target = {
            "slot_name": "default",
            "site_key": "ultrapackv2",
            "item_type_key": "plugin",
            "account_key": "coproducaolancamentos",
        }
        manager = ScraperRunManager()

        class ReusableRun:
            run_id = "target-run"

            @staticmethod
            def is_running() -> bool:
                return False

        manager._find_reusable_run_for_context = lambda _context: ReusableRun()
        calls: list[tuple[str, dict]] = []
        manager.start_run = lambda run_id, **kwargs: calls.append((run_id, kwargs)) or {"message": "Processo iniciado."}

        with patch("app.app.load_run_queue_rules", return_value=[{
            "id": "regra-1", "enabled": True, "source": source, "target": target,
        }]):
            result = manager.trigger_queue_for_context(build_context(source), source_run_id="source-run")

        self.assertEqual(len(result["started"]), 1)
        self.assertEqual(result["skipped"], [])
        self.assertEqual(calls[0][0], "target-run")
        self.assertTrue(calls[0][1]["run_payload"]["triggered_by_queue"])
        self.assertEqual(calls[0][1]["run_payload"]["queue_source_run_id"], "source-run")

    def test_disabled_or_different_source_does_not_start(self) -> None:
        manager = ScraperRunManager()
        manager.start_run = lambda *_args, **_kwargs: self.fail("não deveria iniciar")
        rules = [{
            "id": "regra-1", "enabled": False,
            "source": {"site_key": "plugintheme", "item_type_key": "plugin_theme", "account_key": "coproducaolancamentos", "slot_name": "default"},
            "target": {"site_key": "ultrapackv2", "item_type_key": "plugin", "account_key": "coproducaolancamentos", "slot_name": "default"},
        }]
        with patch("app.app.load_run_queue_rules", return_value=rules):
            result = manager.trigger_queue_for_context(rules[0]["source"])
        self.assertEqual(result, {"started": [], "skipped": []})


if __name__ == "__main__":
    unittest.main()
