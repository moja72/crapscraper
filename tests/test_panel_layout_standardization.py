from pathlib import Path

from app.panel_layout_standardization_policy import (
    _ADDITION_PROGRESS_MARKER,
    _ADDITION_RENDER_MARKER,
    _patch_addition_progress,
)


def test_layout_standardization_script_contract() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert "addition_intro_card" in source
    assert "Adicionar produtos" in source
    assert "addition-layout-standard" in source
    assert "tab_btn_adicoes" in source
    assert "tab_btn_atualizacoes" in source


def test_update_and_addition_share_operational_components() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    for shared_class in (
        "cs-op-card",
        "cs-op-section",
        "cs-op-filterbar",
        "cs-op-list-meta",
        "cs-op-page-size",
        "cs-op-pagination",
        "cs-op-page-jump",
        "cs-op-actions",
        "cs-op-empty",
    ):
        assert shared_class in source
    assert "#tab_panel_atualizacoes" in source
    assert "#tab_panel_adicoes" in source


def test_update_queue_meta_reuses_existing_nodes() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert '$("#updates_queue_found_count"' in source
    assert '$("#updates_queue_page_size"' in source
    assert 'meta.appendChild(found)' in source
    assert 'meta.appendChild(pageLabel)' in source
    assert "cloneNode" not in source


def test_visual_standardization_does_not_add_background_activity() -> None:
    for path in (
        "app/static/panel_layout_standardization.js",
        "app/static/operational_ui_parity.js",
        "app/static/operational_ui_final_alignment.js",
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "MutationObserver" not in source
        assert "setInterval(" not in source
        assert "fetch(" not in source
        assert "XMLHttpRequest" not in source


def test_update_preparation_empty_state_is_deduplicated() -> None:
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "app/static/panel_layout_standardization.js",
            "app/static/operational_ui_parity.js",
            "app/static/operational_ui_final_alignment.js",
        )
    )
    assert "dedupeUpdatePreparationEmpty" in sources
    assert "seen.has(key)" in sources
    assert "node.remove()" in sources


def test_addition_progress_is_patched_into_existing_operational_ui() -> None:
    sample = (
        "before\n"
        + _ADDITION_PROGRESS_MARKER
        + "\n"
        + _ADDITION_RENDER_MARKER
        + "after\n"
    )
    patched = _patch_addition_progress(sample)
    assert 'id="addition_progress_block"' in patched
    assert 'id="addition_progress_percent"' in patched
    assert 'id="addition_progress_label"' in patched
    assert 'id="addition_progress_bar"' in patched
    assert 'id="addition_now"' in patched
    assert "additionProgressTotal" in patched
    assert "additionProgressProcessed" in patched
    assert "aria-valuenow" in patched
    assert "__crapScraperSyncAdditionHistoryTabs?.(counts)" in patched
    assert _patch_addition_progress(patched) == patched


def test_deeper_operational_parity_reuses_existing_nodes() -> None:
    source = Path("app/static/operational_ui_parity.js").read_text(encoding="utf-8")
    assert "mergeAdditionOverview" in source
    assert "standardizeAdditionQueue" in source
    assert "cs-op-overview-card" in source
    assert "cs-op-progress-copy" in source
    assert "cs-op-progress-track" in source
    assert "cs-op-now" in source
    assert "cs-op-queue-primary-actions" in source
    assert 'actions.appendChild(sync)' in source
    assert '[start, pause, recover].forEach(button => actions.appendChild(button))' in source
    assert "summary.remove()" in source
    assert "cloneNode" not in source


def test_addition_history_matches_update_history_structure() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert "standardizeAdditionHistory" in source
    assert 'tabs.id = "addition_history_tabs"' in source
    assert "updates-history-tabs cs-op-history-tabs" in source
    assert "addition_history_completed_tab" in source
    assert "addition_history_errors_tab" in source
    assert 'activateHistoryFilter("completed")' in source
    assert 'activateHistoryFilter("error")' in source
    assert 'meta.insertAdjacentElement("afterend", pagination)' in source
    assert 'filters?.removeAttribute("style")' in source


def test_addition_history_counts_use_existing_overview_counts() -> None:
    policy = Path("app/panel_layout_standardization_policy.py").read_text(encoding="utf-8")
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert "__crapScraperSyncAdditionHistoryTabs?.(counts)" in policy
    assert "window.__crapScraperSyncAdditionHistoryTabs" in source
    assert "counts.completed" in source
    assert "counts.error" in source


def test_addition_history_default_completed_waits_until_history_opens() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert 'accordion.addEventListener("toggle"' in source
    assert "if (!accordion.open" in source
    assert 'activateHistoryFilter("completed")' in source


def test_shared_filters_pagination_cards_and_logs_are_styled_by_final_layer() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    for token in (
        "cs-op-section",
        "cs-op-filterbar",
        "cs-op-history-toolbar",
        "cs-op-actions",
        "cs-op-list-meta",
        "cs-op-pagination",
        "cs-op-page-jump",
        "cs-op-empty",
        "updates-technical-log",
    ):
        assert token in source


def test_standardization_policy_injects_all_visual_layers() -> None:
    source = Path("app/panel_layout_standardization_policy.py").read_text(encoding="utf-8")
    assert "panel_layout_standardization.js" in source
    assert "operational_ui_parity.js" in source
    assert "operational_ui_final_alignment.js" in source
    assert "_patch_addition_progress" in source
    assert "data-operational-ui-parity" in source
    assert "data-operational-ui-final-alignment" in source


def test_process_header_keeps_credits_after_button() -> None:
    source = Path("app/static/processes_header_position.js").read_text(encoding="utf-8")
    assert "cs_processes_header_group" in source
    assert 'group.appendChild(button)' in source
    assert 'group.appendChild(credits)' in source
    assert "display:inline-flex" in source


def test_standardization_policy_is_installed_after_stability_fixes() -> None:
    source = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")
    assert "install_panel_layout_standardization_policy" in source
    assert source.index("install_local_ui_resilience_policy()") < source.index("install_panel_layout_standardization_policy()")
    assert source.index("install_addition_loading_render_fix_policy()") < source.index("install_panel_layout_standardization_policy()")
