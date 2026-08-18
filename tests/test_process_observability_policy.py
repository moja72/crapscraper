from __future__ import annotations

import app.process_observability_policy as policy


class FakeLogs:
    def __init__(self, rows: dict[str, list[str]]) -> None:
        self.rows = rows

    def to_list(self, job_id: str) -> list[str]:
        return list(self.rows.get(str(job_id), []))


def test_current_history_ready_requires_current_completed_record() -> None:
    base = {
        "state": "completed",
        "completed_at": "2026-08-18T19:00:00+00:00",
        "executing_at": "2026-08-18T18:59:00+00:00",
    }
    assert policy._current_history_ready({**base, "execution_history": []}) is False
    assert policy._current_history_ready({
        **base,
        "execution_history": [{"completed_at": "2026-08-18T18:00:00+00:00"}],
    }) is False
    assert policy._current_history_ready({
        **base,
        "execution_history": [{"completed_at": "2026-08-18T19:00:00+00:00"}],
    }) is True


def test_materialize_projection_prefers_live_logs(monkeypatch) -> None:
    rows = [{
        "job_id": "job-1",
        "state": "executing",
        "execution_logs": ["persistido"],
        "execution_history": [],
    }]
    monkeypatch.setattr(policy, "_BASE_MATERIALIZE", lambda *args, **kwargs: rows)
    monkeypatch.setattr(policy.web, "_UPDATE_LOGS", FakeLogs({"job-1": ["linha 1", "linha 2"]}))

    result = policy._patched_materialize_update_jobs()

    assert result[0]["live_execution_logs"] == ["linha 1", "linha 2"]
    assert result[0]["live_log_tail"] == "linha 2"
    assert result[0]["live_log_count"] == 2
    assert result[0]["history_ready"] is False
    assert "live_execution_logs" not in rows[0]


def test_materialize_projection_falls_back_to_persisted_logs(monkeypatch) -> None:
    rows = [{
        "job_id": "job-2",
        "state": "completed",
        "completed_at": "2026-08-18T19:10:00+00:00",
        "execution_logs": ["fim persistido"],
        "execution_history": [{"completed_at": "2026-08-18T19:10:00+00:00"}],
    }]
    monkeypatch.setattr(policy, "_BASE_MATERIALIZE", lambda *args, **kwargs: rows)
    monkeypatch.setattr(policy.web, "_UPDATE_LOGS", FakeLogs({}))

    result = policy._patched_materialize_update_jobs()

    assert result[0]["live_execution_logs"] == []
    assert result[0]["live_log_tail"] == "fim persistido"
    assert result[0]["live_log_count"] == 1
    assert result[0]["history_ready"] is True
