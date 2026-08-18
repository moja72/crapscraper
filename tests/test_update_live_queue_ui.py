from __future__ import annotations

from pathlib import Path


def test_update_queue_keeps_completed_filter_and_live_log_contract() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "update_queue_fix.js"
    ).read_text(encoding="utf-8")

    assert '"completed"' in script
    assert "history_ready" in script
    assert "live_execution_logs" in script
    assert "cs-update-live-log" in script
    assert "Finalizando registro no histórico" in script
    assert "currentStateFilter" in script
    assert "if (stateFilter) return state === stateFilter" in script

    for state in (
        "installing",
        "filesystem_validated",
        "updating_wordpress",
        "validating_wordpress",
        "rolling_back",
    ):
        assert state in script


def test_operational_filter_exposes_completed_and_intermediate_states() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "update_operational_filters.js"
    ).read_text(encoding="utf-8")

    assert '["completed", "Concluído"]' in script
    assert '["installing", "Instalando"]' in script
    assert '["updating_wordpress", "Atualizando WordPress"]' in script
    assert '["validating_wordpress", "Validando WordPress"]' in script
