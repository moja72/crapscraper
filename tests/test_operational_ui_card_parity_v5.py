from pathlib import Path


FRONTEND = Path("app/static/operational_ui_card_parity_v5.js")
PANEL_POLICY = Path("app/panel_layout_standardization_policy.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_update_and_addition_use_same_five_column_card_grid() -> None:
    source = _read(FRONTEND)
    assert "#updates_summary,\n      #addition_summary_grid" in source
    assert "grid-template-columns:repeat(5,minmax(0,1fr))!important" in source
    for token in (
        "min-height:66px!important",
        "padding:9px 10px!important",
        "border-radius:10px!important",
        "font-size:18px!important",
        "gap:5px!important",
        "operational-summary-help",
        "width:22px!important",
        "is-filter-active",
    ):
        assert token in source


def test_both_metric_groups_are_clickable_and_filterable() -> None:
    source = _read(FRONTEND)
    for token in (
        "UPDATE_FILTERS",
        "ADDITION_FILTERS",
        "activateUpdateCard",
        "activateAdditionCard",
        'setAttribute("role", "button")',
        'setSelect("updates_status_filter"',
        'setSelect("updates_queue_status_filter"',
        'setSelect("addition_queue_state"',
        "updates_history_completed",
        "updates_history_errors",
        "aria-pressed",
    ):
        assert token in source


def test_help_button_never_triggers_card_filter() -> None:
    source = _read(FRONTEND)
    assert 'event.target?.closest?.(".comparison-help")' in source
    assert "event.stopImmediatePropagation()" in source
    assert 'help.classList.add("operational-summary-help")' in source


def test_final_card_layer_has_no_polling_or_global_mutation_observer() -> None:
    source = _read(FRONTEND)
    assert "setInterval(" not in source
    assert "observe(document.body" not in source
    assert "observe(document.documentElement" not in source
    assert "observe(updateRoot, {childList:true})" in source
    assert "observe(additionRoot, {childList:true})" in source


def test_panel_loads_card_parity_after_previous_alignment_layers() -> None:
    source = _read(PANEL_POLICY)
    assert "data-operational-ui-consistency-v4" in source
    assert "data-operational-ui-card-parity-v5" in source
    assert source.index("data-operational-ui-consistency-v4") < source.index("data-operational-ui-card-parity-v5")
