from __future__ import annotations

from pathlib import Path


def test_real_executor_records_completion_before_returning_success() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app" / "operations" / "real_executor.py"
    ).read_text(encoding="utf-8")

    completed = source.index('job.set_state(JobState.COMPLETED, "Atualização individual concluída")')
    history = source.index('record_execution_outcome(job, dict(plan), "completed")')
    log = source.index('self.log(" Atualização concluída")')
    returned = source.index('return {"ok": True, "state": job.state.value')

    assert completed < history < log < returned
