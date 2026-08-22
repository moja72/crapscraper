from pathlib import Path


FRONTEND = Path("app/static/operational_ui_consistency_v4.js")
QUEUE_POLICY = Path("app/addition_queue_lists_policy.py")
PANEL_POLICY = Path("app/panel_layout_standardization_policy.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_top_cards_share_compact_filterable_design() -> None:
    source = _read(FRONTEND)
    for token in (
        "#updates_summary",
        "#addition_summary_grid",
        "cs-v4-metric-card",
        "min-height:64px",
        "is-filter-active",
        "UPDATE_TOP_FILTERS",
        'role", "button',
        "applyUpdateTopFilter",
        "comparison-help",
    ):
        assert token in source
    assert 'event?.target?.closest?.(".comparison-help")' in source
    assert "event.stopPropagation()" in source


def test_update_preparation_uses_addition_like_filter_structure_and_dedupes_empty_state() -> None:
    source = _read(FRONTEND)
    for token in (
        "standardizeUpdatePreparation",
        "cs-v4-preparation-head",
        "cs-v4-preparation-hint",
        "cs-v4-preparation-filters",
        "cs-v4-preparation-advanced",
        "cs-v4-preparation-refresh",
        "dedupePreparationNotices",
        "updates_search_filter",
        "updates_status_filter",
        "updates_refresh_btn",
    ):
        assert token in source


def test_addition_queue_lists_are_persistent_and_scoped() -> None:
    source = _read(QUEUE_POLICY)
    for token in (
        "addition_queue_lists",
        "queue_name TEXT NOT NULL DEFAULT 'default'",
        "active_queue TEXT NOT NULL DEFAULT 'default'",
        "_counts_scoped",
        "_where_jobs_scoped",
        "_next_queued_job_scoped",
        "_start_queue_scoped",
        '"/adicoes/fila/listas"',
        'action == "create"',
        'action == "select"',
        'action == "rename"',
        'action == "delete"',
        'action == "move"',
    ):
        assert token in source


def test_addition_queue_frontend_exposes_active_list_and_manager_without_replacing_existing_actions() -> None:
    source = _read(FRONTEND)
    for token in (
        "addition_queue_list_select",
        "open_addition_lists_modal",
        "Gerenciar Listas de Adições",
        "addition_list_create",
        "addition_list_move_selected",
        "[data-add-select='queue']:checked",
        "addition_queue_start",
        "addition_queue_pause",
        "addition_queue_refresh",
    ):
        assert token in source


def test_addition_history_matches_update_history_and_can_clear_attempt_history() -> None:
    frontend = _read(FRONTEND)
    backend = _read(QUEUE_POLICY)
    for token in (
        'title.textContent = "Histórico"',
        "addition_history_tabs",
        "updates-history-tab.is-active",
        "addition_history_delete",
        "Apagar histórico",
        '"/adicoes/operacoes/historico/limpar"',
        "addition_history_download",
    ):
        assert token in frontend or token in backend
    assert "DELETE FROM addition_attempt_history" in backend


def test_final_layer_has_no_polling_or_global_mutation_observer() -> None:
    source = _read(FRONTEND)
    assert "setInterval(" not in source
    assert "observe(document.body" not in source
    assert "observe(document.documentElement" not in source
    assert "new MutationObserver" in source
    assert "observe(updateRoot, {childList:true})" in source
    assert "observe(additionRoot, {childList:true})" in source
    assert "observe(jobs, {childList:true})" in source


def test_panel_policy_installs_queue_lists_before_final_visual_layer() -> None:
    source = _read(PANEL_POLICY)
    assert "data-operational-ui-consistency-v4" in source
    assert "install_addition_queue_lists_policy" in source
    assert source.index("install_addition_queue_lists_policy()") < source.index("web.render_panel_page = _patched_render_panel_page")
