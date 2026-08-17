from __future__ import annotations

from pathlib import Path

from app.operations.transient_recovery import recover_payload


def test_transient_preparation_returns_to_approved_without_losing_staging() -> None:
    payload = {
        "jobs": [{
            "job_id": "JOB-1",
            "woo_product_id": 123,
            "name": "Produto",
            "state": "validating",
            "queue_position": 18,
            "local_staging_path": r"data\staging\updates\JOB-1\produto.zip",
            "new_sha256": "a" * 64,
            "diagnostics": [],
            "execution_history": [],
        }]
    }

    repaired, changes = recover_payload(payload)
    job = repaired["jobs"][0]

    assert len(changes) == 1
    assert job["state"] == "approved"
    assert job["queue_position"] == 0
    assert job["local_staging_path"].endswith("produto.zip")
    assert job["new_sha256"] == "a" * 64
    assert "interrompida" in job["execution_error"].lower()
    assert job["execution_history"][-1]["result"] == "preparation_interrupted"


def test_terminal_and_ready_states_are_not_changed() -> None:
    payload = {"jobs": [
        {"job_id": "A", "state": "completed"},
        {"job_id": "B", "state": "plan_ready"},
        {"job_id": "C", "state": "blocked"},
    ]}
    repaired, changes = recover_payload(payload)
    assert changes == []
    assert [item["state"] for item in repaired["jobs"]] == ["completed", "plan_ready", "blocked"]


def test_operational_filter_script_exposes_real_states_and_zip_indicator() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "app" / "static" / "update_operational_filters.js").read_text(encoding="utf-8")
    policy = (root / "app" / "update_operational_ui_policy.py").read_text(encoding="utf-8")

    for state in (
        "approved", "validating", "plan_ready", "queued", "executing",
        "completed", "blocked", "error", "rollback_required",
    ):
        assert f'"{state}"' in script
    assert "ZIP local registrado" in script
    assert "local_staging_path" in script
    assert "new_sha256" in script
    assert "data-update-operational-filters" in policy
