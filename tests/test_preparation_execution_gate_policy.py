from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app.preparation_execution_gate_policy as gate
import app.update_queue_lifecycle_policy as update_lifecycle


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("esta operação não deveria ter sido chamada")


class PreparationExecutionGateTests(unittest.TestCase):
    def test_update_plan_ready_is_not_auto_enqueued(self):
        saved = {"ready": True, "state": "ready_for_homologation"}
        with (
            patch.object(update_lifecycle, "_BASE_SAVE_PLAN", lambda _job_id, _plan: saved),
            patch.object(update_lifecycle.runtime, "enqueue_jobs", _fail_if_called),
        ):
            result = update_lifecycle._save_plan("job-1", {"ready": True})

        self.assertIs(result, saved)

    def test_add_selected_queues_only_ready_and_does_not_start_execution(self):
        rows = {
            "ready": {
                "job_id": "ready",
                "approval_active": 1,
                "queue_state": "ready",
                "state": "ready_to_create",
                "active_attempt_id": 0,
            },
            "waiting": {
                "job_id": "waiting",
                "approval_active": 1,
                "queue_state": "waiting",
                "state": "awaiting_content",
                "active_attempt_id": 0,
            },
        }
        queued: list[str] = []

        with (
            patch.object(gate.additions_ui, "_normalize_job_ids", lambda _payload: ["ready", "waiting"]),
            patch.object(gate.additions_ui, "_job_snapshot", lambda job_id: dict(rows[job_id])),
            patch.object(gate.additions_ui, "_prepared_local", lambda row: row.get("queue_state") == "ready"),
            patch.object(gate.additions_ui, "_enqueue_ready", lambda job_id: queued.append(job_id)),
            patch.object(gate.additions_ui, "_queue_runtime", lambda: {"status": "stopped"}),
            patch.object(gate.additions_ui, "_set_queue_runtime", _fail_if_called),
            patch.object(gate.additions_ui, "_start_queue_worker", _fail_if_called),
        ):
            result = gate._request_add({"job_ids": ["ready", "waiting"]}, manager=None)

        self.assertEqual(queued, ["ready"])
        self.assertEqual(result["queued"], 1)
        self.assertEqual(result["not_ready"], 1)
        self.assertEqual(result["queue"]["status"], "stopped")

    def test_retry_returns_to_preparation_without_auto_enqueue(self):
        row = {
            "job_id": "erro-1",
            "approval_active": 1,
            "queue_state": "error",
            "state": "awaiting_content",
            "active_attempt_id": 0,
        }
        changes: list[dict] = []
        workers: list[object] = []

        with (
            patch.object(gate.additions_ui, "_normalize_job_ids", lambda _payload: ["erro-1"]),
            patch.object(gate.additions_ui, "_job_snapshot", lambda _job_id: dict(row)),
            patch.object(gate.additions_ui, "_prepared_local", lambda _row: False),
            patch.object(
                gate.additions_ui,
                "_update_operation",
                lambda _job_id, **values: changes.append(values) or dict(row),
            ),
            patch.object(
                gate.additions_ui,
                "_start_preparation_worker",
                lambda manager: workers.append(manager) or True,
            ),
            patch.object(gate.additions_ui, "_queue_runtime", lambda: {"status": "stopped"}),
            patch.object(gate.additions_ui, "_enqueue_ready", _fail_if_called),
            patch.object(gate.additions_ui, "_set_queue_runtime", _fail_if_called),
            patch.object(gate.additions_ui, "_start_queue_worker", _fail_if_called),
        ):
            result = gate._request_add({"job_ids": ["erro-1"]}, manager="manager", retry=True)

        self.assertEqual(result["preparing"], 1)
        self.assertEqual(result["queued"], 0)
        self.assertEqual(workers, ["manager"])
        self.assertTrue(changes)
        self.assertEqual(changes[-1]["queue_state"], "preparing")
        self.assertEqual(changes[-1]["enqueue_after_prepare"], 0)

    def test_start_queue_does_not_promote_ready_items(self):
        class Cursor:
            def __init__(self, total: int):
                self.total = total

            def fetchone(self):
                return {"total": self.total}

        class Connection:
            def execute(self, sql: str):
                if "queue_state='queued'" in sql:
                    return Cursor(0)
                if "queue_state='executing'" in sql:
                    return Cursor(0)
                raise AssertionError(sql)

        @contextmanager
        def fake_db():
            yield Connection()

        with (
            patch.object(gate.additions_ui, "_renumber_queue", lambda: None),
            patch.object(gate.additions_ui.additions, "_db", fake_db),
            patch.object(gate.additions_ui, "_enqueue_ready", _fail_if_called),
            patch.object(gate.additions_ui, "_start_queue_worker", _fail_if_called),
            patch.object(gate.additions_ui, "_set_queue_runtime", lambda status: {"status": status}),
        ):
            result = gate._start_queue()

        self.assertFalse(result["started"])
        self.assertEqual(result["queue"]["status"], "stopped")
        self.assertIn("Adicionar à fila", result["message"])

    def test_preparation_ui_v10_uses_shared_component_without_observer_or_polling(self):
        script = Path("app/static/preparation_flow_gate_v10.js").read_text(encoding="utf-8")

        self.assertIn("cs-preparation-unified", script)
        self.assertIn("data-cs-preparation-role", script)
        self.assertIn("Preparar selecionados", script)
        self.assertIn("Adicionar selecionados à fila", script)
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("setInterval", script)


if __name__ == "__main__":
    unittest.main()
