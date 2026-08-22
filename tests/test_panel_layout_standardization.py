from pathlib import Path


def test_layout_standardization_script_contract() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert "addition_intro_card" in source
    assert "Adicionar produtos" in source
    assert "addition-layout-standard" in source
    assert "addition_summary_grid" not in source or "addition-summary-grid" in source
    assert "tab_btn_adicoes" in source


def test_update_and_addition_share_operational_components() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")

    for component in (
        "cs-operational-section",
        "cs-operational-filters",
        "cs-operational-meta",
        "cs-operational-actions",
        "cs-operational-list",
        "cs-operational-pagination",
        "cs-operational-stats",
    ):
        assert component in source

    assert "standardizeUpdates" in source
    assert "standardizeAddition" in source
    assert 'insertAdjacentElement("afterend", prepPagination)' in source
    assert 'insertAdjacentElement("afterend", queuePagination)' in source
    assert 'insertAdjacentElement("afterend", historyPagination)' in source


def test_page_jump_preserves_existing_controls_and_scopes_observers() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")

    assert "repairPageJump" in source
    assert "updatesWaiting" in source
    assert "updatesQueue" in source
    assert "updatesHistory" in source
    assert 'observer.observe(label, {childList:true})' in source
    assert ".observe(document.body" not in source
    assert ".observe(document.documentElement" not in source


def test_update_operational_filter_has_no_global_dom_observer() -> None:
    source = Path("app/static/update_operational_filters.js").read_text(encoding="utf-8")

    assert "panelVisible()" in source
    assert 'key === "atualizacoes"' in source
    assert "MutationObserver" not in source
    assert ".observe(document.body" not in source
    assert "if (panelVisible() && !document.hidden)" in source


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
