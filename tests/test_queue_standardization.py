from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.queue_standardization_policy as policy
from app.operations.models import JobState


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "static" / "queue_standardization_v1.js"
COMPAT_SCRIPT = ROOT / "app" / "static" / "queue_standardization_v1_compat.js"


class DummyJob(SimpleNamespace):
    def set_state(self, state, _message):
        self.state = state


class QueueStandardizationTests(unittest.TestCase):
    def test_render_injects_final_queue_scripts(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda: "<html><body>painel</body></html>"
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original
        self.assertIn('data-queue-standardization-v1="1"', html)
        self.assertIn('data-queue-standardization-v1="2"', html)
        self.assertIn("cs-queue-v1", html)
        self.assertIn("ensureUpdateQueueMetaContract", html)

    def test_script_contains_shared_queue_contract(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        required = [
            "cs-queue-v1-management",
            "cs-queue-v1-selector",
            "cs-queue-v1-primary",
            "cs-queue-v1-summary-grid",
            "cs-queue-v1-filterbar",
            "cs-queue-v1-meta",
            "cs-queue-v1-bulk",
            "Selecionar todo resultado",
            "Limpar seleção",
            "Adicionar selecionados à fila",
            "Tentar novamente",
            "Cancelar selecionados",
            "Limpar concluídos da fila",
            "cs-queue-v1-list",
            "cs-queue-v1-pagination",
        ]
        for value in required:
            self.assertIn(value, script)
        self.assertIn("normalizeUpdateQueue", script)
        self.assertIn("normalizeAdditionQueue", script)
        self.assertIn("cs_addition_queue_summary_v1", script)

    def test_compat_preserves_meta_and_enforces_queue_visual_parity(self) -> None:
        script = COMPAT_SCRIPT.read_text(encoding="utf-8")
        required = [
            '$("#updates_queue_meta")',
            'meta.id = "updates_queue_meta"',
            "MutationObserver",
            "cs_updates_queue_summary_v1",
            "cs-queue-v1-state-hidden",
            "cs-queue-v1-no-state",
            "Rollback necessário",
            "data-tooltip",
            "addition_queue_recover",
            "addition_queue_search",
            "order:80!important",
            '[class*="pagination"]',
            "border-radius:999px!important",
            "cs-queue-v1-total-filter",
        ]
        for value in required:
            self.assertIn(value, script)

    def test_cancel_selected_updates_only_cancels_queued_active_jobs(self) -> None:
        queued = DummyJob(queue_name="default", state=JobState.QUEUED, canceled_at="", queue_position=2)
        completed = DummyJob(queue_name="default", state=JobState.COMPLETED, canceled_at="", queue_position=0)
        other_queue = DummyJob(queue_name="other", state=JobState.QUEUED, canceled_at="", queue_position=1)
        jobs = {"q": queued, "done": completed, "other": other_queue}
        with patch.object(policy.runtime, "_JOBS", jobs), \
             patch.object(policy.runtime, "_QUEUE_CONTROL", {"active_queue": "default", "status": "stopped", "queues": {"default": {}}}), \
             patch.object(policy.runtime, "_persist"), \
             patch.object(policy.runtime, "queue_snapshot", return_value={"status": "stopped"}):
            result = policy._cancel_selected_updates(["q", "done", "other", "missing"])
        self.assertEqual(result["canceled"], 1)
        self.assertEqual(queued.state, JobState.CANCELED)
        self.assertEqual(queued.queue_position, 0)
        self.assertEqual(completed.state, JobState.COMPLETED)
        self.assertEqual(other_queue.state, JobState.QUEUED)

    def test_clear_completed_only_removes_completed_from_active_visual_queue(self) -> None:
        completed = DummyJob(queue_name="default", state=JobState.COMPLETED, queue_position=0, queued_at="old")
        queued = DummyJob(queue_name="default", state=JobState.QUEUED, queue_position=2, queued_at="now")
        other = DummyJob(queue_name="other", state=JobState.COMPLETED, queue_position=0, queued_at="old")
        jobs = {"done": completed, "queued": queued, "other": other}
        with patch.object(policy.runtime, "_JOBS", jobs), \
             patch.object(policy.runtime, "_QUEUE_CONTROL", {"active_queue": "default", "status": "stopped", "queues": {"default": {}}}), \
             patch.object(policy.runtime, "_persist"), \
             patch.object(policy.runtime, "queue_snapshot", return_value={"status": "stopped"}):
            result = policy._clear_completed_update_queue()
        self.assertEqual(result["removed"], 1)
        self.assertEqual(completed.queue_name, "")
        self.assertEqual(completed.queued_at, "")
        self.assertEqual(queued.queue_name, "default")
        self.assertEqual(other.queue_name, "other")


if __name__ == "__main__":
    unittest.main()
