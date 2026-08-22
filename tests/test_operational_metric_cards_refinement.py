from pathlib import Path


SOURCE = Path("app/static/update_operational_filters.js")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_addition_cards_use_shared_metric_language_and_help() -> None:
    source = _source()
    for token in (
        "ADDITION_HELP",
        "operational-summary-grid",
        "operational-summary-footer",
        "operational-summary-label",
        "operational-summary-help",
        "Total aprovado",
        "Com erro",
        "Cancelado",
    ):
        assert token in source
    assert "#addition_summary_grid.operational-summary-grid" in source
    assert 'card.setAttribute("role", "button")' in source
    assert 'select.value = ""' in source


def test_update_queue_cards_keep_click_filtering_and_help() -> None:
    source = _source()
    for token in (
        "UPDATE_HELP",
        "data-cs-update-state",
        "selectState(button.dataset.csUpdateState || \"\")",
        "is-filter-active",
        "ZIP local registrado",
        "Rollback necessário",
    ):
        assert token in source
    assert 'event.target.closest?.(".comparison-help")' in source
    assert "event.stopPropagation()" in source


def test_update_queue_controls_are_compact_and_have_contextual_help() -> None:
    source = _source()
    for token in (
        "operational-queue-controls",
        "operational-action-grid",
        "operational-action-help",
        "operational-field-help",
        "updates_queue_search",
        "updates_queue_status_filter",
        "updates_queue_page_size",
    ):
        assert token in source
    assert "gap:10px!important" in source
    assert "margin:0!important" in source


def test_refinement_does_not_restore_global_polling_or_global_dom_observer() -> None:
    source = _source()
    assert "setInterval(" not in source
    assert "observe(document.body" not in source
    assert '$("#updates_queue_jobs")' in source
    assert '$("#addition_summary_grid")' in source
    assert "new MutationObserver" in source
    assert ".observe(rows, {childList:true})" in source
    assert ".observe(root, {childList:true})" in source
