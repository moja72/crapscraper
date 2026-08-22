from pathlib import Path


FRONTEND = Path("app/static/operational_ui_card_size_parity_v6.js")
PANEL_POLICY = Path("app/panel_layout_standardization_policy.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_update_and_addition_cards_use_same_desktop_grid_and_geometry() -> None:
    source = _read(FRONTEND)
    assert "#updates_summary" in source
    assert "#addition_summary_grid" in source
    assert "grid-template-columns:repeat(7,minmax(0,1fr))" in source
    assert "min-height:66px" in source
    assert "padding:9px 10px" in source
    assert "grid-column:auto" in source


def test_help_buttons_keep_identical_size() -> None:
    source = _read(FRONTEND)
    assert "width:22px" in source
    assert "height:22px" in source
    assert "operational-summary-help" in source


def test_size_layer_does_not_add_polling_or_global_observers() -> None:
    source = _read(FRONTEND)
    assert "setInterval(" not in source
    assert "MutationObserver" not in source
    assert "fetch(" not in source


def test_size_layer_loads_after_v5_behavior_layer() -> None:
    source = _read(PANEL_POLICY)
    v5 = 'data-operational-ui-card-parity-v5'
    v6 = 'data-operational-ui-card-size-parity-v6'
    assert v5 in source and v6 in source
    assert source.index(v5) < source.index(v6)
