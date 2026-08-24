from __future__ import annotations

import unittest
from pathlib import Path


class QueueHelpCleanupContractTests(unittest.TestCase):
    def test_queue_policy_injects_cleanup_after_standardization(self) -> None:
        policy = Path("app/queue_standardization_policy.py").read_text(encoding="utf-8")
        self.assertIn('"queue_help_cleanup_v2.js"', policy)

    def test_cleanup_removes_wrappers_without_real_controls(self) -> None:
        script = Path("app/static/queue_help_cleanup_v2.js").read_text(encoding="utf-8")
        self.assertIn("if (!realButton) wrapper.remove()", script)
        self.assertIn("comparison-help.operational-action-help", script)
        self.assertIn("comparison-help.operational-field-help", script)
        self.assertIn("MutationObserver", script)


if __name__ == "__main__":
    unittest.main()
