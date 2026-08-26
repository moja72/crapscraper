from pathlib import Path


FRONTEND = Path("app/static/operational_ui_card_size_parity_v6.js")
PANEL_POLICY = Path("app/panel_layout_standardization_policy.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_update_and_addition_cards_use_same_explicit_desktop_geometry() -> None:
    source = _read(FRONTEND)
    assert "#tab_panel_atualizacoes #updates_summary" in source
    assert "#addition_intro_card #addition_summary_grid" in source
    assert "#addition_intro_card #addition_summary_grid>.addition-summary-chip" in source
    assert "grid-template-columns:repeat(auto-fill,200px)" in source
    assert "column-gap:8px" in source
    assert "row-gap:8px" in source
    assert "justify-content:start" in source
    assert "width:200px" in source
    assert "min-width:200px" in source
    assert "max-width:200px" in source
    assert "height:66px" in source
    assert "min-height:66px" in source
    assert "max-height:66px" in source
    assert "padding:9px 10px" in source


def test_specificity_prevents_legacy_grid_from_redistributing_free_space() -> None:
    source = _read(FRONTEND)
    assert "#tab_panel_atualizacoes #updates_summary" in source
    assert "#addition_intro_card #addition_summary_grid" in source
    assert "grid-auto-columns:200px" in source
    assert "justify-items:start" in source
    assert "justify-self:start" in source


def test_update_and_addition_cards_share_typography_footer_and_active_state() -> None:
    source = _read(FRONTEND)
    assert "#tab_panel_atualizacoes #updates_summary>*>strong" in source
    assert "#addition_intro_card #addition_summary_grid>*>strong" in source
    assert "font-size:18px" in source
    assert ".operational-summary-footer" in source
    assert "#tab_panel_atualizacoes #updates_summary>.is-filter-active" in source
    assert "#addition_intro_card #addition_summary_grid>.is-filter-active" in source


def test_help_buttons_keep_identical_size() -> None:
    source = _read(FRONTEND)
    assert "#tab_panel_atualizacoes #updates_summary .comparison-help" in source
    assert "#addition_intro_card #addition_summary_grid .comparison-help" in source
    assert "width:22px" in source
    assert "height:22px" in source


def test_size_layer_does_not_add_polling_fetch_or_observers() -> None:
    source = _read(FRONTEND)
    assert "setInterval(" not in source
    assert "MutationObserver" not in source
    assert "fetch(" not in source


def test_size_layer_loads_without_removed_v5_behavior_layer() -> None:
    source = _read(PANEL_POLICY)
    assert "data-operational-ui-card-parity-v5" not in source
    assert "data-operational-ui-card-size-parity-v6" in source
