from pathlib import Path


def test_layout_standardization_script_contract() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert "addition_intro_card" in source
    assert "Adicionar produtos" in source
    assert "addition-layout-standard" in source
    assert "addition_summary_grid" not in source or "addition-summary-grid" in source
    assert "tab_btn_adicoes" in source


def test_process_header_keeps_credits_after_button() -> None:
    source = Path("app/static/processes_header_position.js").read_text(encoding="utf-8")
    assert "cs_processes_header_group" in source
    assert 'group.appendChild(button)' in source
    assert 'group.appendChild(credits)' in source
    assert "display:inline-flex" in source


def test_standardization_policy_is_installed_last() -> None:
    source = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")
    assert "install_panel_layout_standardization_policy" in source
    assert source.index("install_local_ui_resilience_policy()") < source.index("install_panel_layout_standardization_policy()")
