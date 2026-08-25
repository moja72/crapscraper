from pathlib import Path


def test_process_history_global_observer_is_disabled_by_final_render_policy() -> None:
    policy = Path("app/process_modal_stability_policy.py").read_text(encoding="utf-8")
    assert '"    observeUi();\\n"' in policy
    assert "_PROCESS_HISTORY_SAFE_BOOT" in policy
    assert "html.replace(_PROCESS_HISTORY_OBSERVER_BOOT, _PROCESS_HISTORY_SAFE_BOOT)" in policy


def test_processes_header_moves_synchronously_on_dom_ready() -> None:
    script = Path("app/static/processes_header_position.js").read_text(encoding="utf-8")
    schedule = script.split("function scheduleMove()", 1)[1].split("installCreditFreezeGuard();", 1)[0]
    assert "moveProcessesButton();" in schedule
    assert "[60, 180, 450, 900, 1800, 2600]" in schedule
    assert schedule.index("moveProcessesButton();") < schedule.index("setTimeout(moveProcessesButton")
