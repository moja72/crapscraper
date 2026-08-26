from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.deferred_runtime_bootstrap import (
    defer_runtime_file_for_imports,
    restore_deferred_runtime_file,
)


class DeferredRuntimeBootstrapTests(unittest.TestCase):
    def test_runtime_file_is_hidden_during_import_window_and_restored_losslessly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "update_runtime.json"
            payload = '{"jobs":[{"job_id":"abc"}]}'
            path.write_text(payload, encoding="utf-8")

            deferred = defer_runtime_file_for_imports(path)
            deferred_path = Path(deferred["deferred_path"])

            self.assertTrue(deferred["deferred"])
            self.assertFalse(path.exists())
            self.assertTrue(deferred_path.exists())
            self.assertEqual(deferred_path.read_text(encoding="utf-8"), payload)

            restored = restore_deferred_runtime_file(path)
            self.assertTrue(restored["restored"])
            self.assertTrue(path.exists())
            self.assertFalse(deferred_path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), payload)

    def test_stale_deferred_file_from_interrupted_boot_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "update_runtime.json"
            deferred_path = path.with_suffix(path.suffix + ".boot-deferred")
            deferred_path.write_text("persisted", encoding="utf-8")

            result = defer_runtime_file_for_imports(path)

            self.assertTrue(result["deferred"])
            self.assertTrue(result["recovered_stale_boot"])
            self.assertFalse(path.exists())
            self.assertTrue(deferred_path.exists())

            restore_deferred_runtime_file(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "persisted")

    def test_main_defers_runtime_before_importing_scraper_app(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        defer_pos = source.index("_RUNTIME_DEFER_INFO = defer_runtime_file_for_imports()")
        app_import_pos = source.index("from app.app import ScraperApp")
        self.assertLess(defer_pos, app_import_pos)
        self.assertNotIn("\nrepair_update_runtime()\nrecover_interrupted_preparations()\n", source)
        self.assertIn("start_runtime_recovery_background(", source)
        self.assertIn("install_startup_runtime_gate_policy()", source)


if __name__ == "__main__":
    unittest.main()
