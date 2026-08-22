from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import app.preparation_execution_gate_policy as gate
import app.update_queue_lifecycle_policy as update_lifecycle


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("esta operação não deveria ter sido chamada")


def test_update_plan_ready_is_not_auto_enqueued(monkeypatch):
    saved = {"ready": True, "state": "ready_for_homologation"}
    monkeypatch.setattr(update_lifecycle, "_BASE_SAVE_PLAN", lambda _job_id, _plan: saved)
    monkeypatch.setattr(update_lifecycle.runtime, "enqueue_jobs", _fail_if_called)

    result = update_lifecycle._save_plan("job-1", {"ready": True})

    assert result is saved


def test_add_selected_queues_only_ready_and_does_not_start_execution(monkeypatch):
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

    monkeypatch.setattr(gate.additions_ui, "_normalize_job_ids", lambda _payload: ["ready", "waiting"])
    monkeypatch.setattr(gate.additions_ui, "_job_snapshot", lambda job_id: dict(rows[job_id]))
    monkeypatch.setattr(gate.additions_ui, "_prepared_local", lambda row: row.get("queue_state") == "ready")
    monkeypatch.setattr(gate.additions_ui, "_enqueue_ready", lambda job_id: queued.append(job_id))
    monkeypatch.setattr(gate.additions_ui, "_queue_runtime", lambda: {"status": "stopped"})
    monkeypatch.setattr(gate.additions_ui, "_set_queue_runtime", _fail_if_called)
    monkeypatch.setattr(gate.additions_ui, "_start_queue_worker", _fail_if_called)

    result = gate._request_add({"job_ids": ["ready", "waiting"]}, manager=None)

    assert queued == ["ready"]
    assert result["queued"] == 1
    assert result["not_ready"] == 1
    assert result["queue"]["status"] == "stopped"


def test_retry_returns_to_preparation_without_auto_enqueue(monkeypatch):
    row = {
        "job_id": "erro-1",
        "approval_active": 1,
        "queue_state": "error",
        "state": "awaiting_content",
        "active_attempt_id": 0,
    }
    changes: list[dict] = []
    workers: list[object] = []

    monkeypatch.setattr(gate.additions_ui, "_normalize_job_ids", lambda _payload: ["erro-1"])
    monkeypatch.setattr(gate.additions_ui, "_job_snapshot", lambda _job_id: dict(row))
    monkeypatch.setattr(gate.additions_ui, "_prepared_local", lambda _row: False)
    monkeypatch.setattr(gate.additions_ui, "_update_operation", lambda _job_id, **values: changes.append(values) or dict(row))
    monkeypatch.setattr(gate.additions_ui, "_start_preparation_worker", lambda manager: workers.append(manager) or True)
    monkeypatch.setattr(gate.additions_ui, "_queue_runtime", lambda: {"status": "stopped"})
    monkeypatch.setattr(gate.additions_ui, "_enqueue_ready", _fail_if_called)
    monkeypatch.setattr(gate.additions_ui, "_set_queue_runtime", _fail_if_called)
    monkeypatch.setattr(gate.additions_ui, "_start_queue_worker", _fail_if_called)

    result = gate._request_add({"job_ids": ["erro-1"]}, manager="manager", retry=True)

    assert result["preparing"] == 1
    assert result["queued"] == 0
    assert workers == ["manager"]
    assert changes and changes[-1]["queue_state"] == "preparing"
    assert changes[-1]["enqueue_after_prepare"] == 0


def test_start_queue_does_not_promote_ready_items(monkeypatch):
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

    monkeypatch.setattr(gate.additions_ui, "_renumber_queue", lambda: None)
    monkeypatch.setattr(gate.additions_ui.additions, "_db", fake_db)
    monkeypatch.setattr(gate.additions_ui, "_enqueue_ready", _fail_if_called)
    monkeypatch.setattr(gate.additions_ui, "_start_queue_worker", _fail_if_called)
    monkeypatch.setattr(
        gate.additions_ui,
        "_set_queue_runtime",
        lambda status: {"status": status},
    )

    result = gate._start_queue()

    assert result["started"] is False
    assert result["queue"]["status"] == "stopped"
    assert "Adicionar à fila" in result["message"]


def test_preparation_ui_v10_uses_shared_component_without_observer_or_polling():
    script = Path("app/static/preparation_flow_gate_v10.js").read_text(encoding="utf-8")

    assert "cs-preparation-unified" in script
    assert "data-cs-preparation-role" in script
    assert "Preparar selecionados" in script
    assert "Adicionar selecionados à fila" in script
    assert "MutationObserver" not in script
    assert "setInterval" not in script
