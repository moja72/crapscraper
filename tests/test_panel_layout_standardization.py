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


def test_update_queue_meta_reuses_existing_nodes() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert '$("#updates_queue_found_count"' in source
    assert '$("#updates_queue_page_size"' in source
    assert "meta.appendChild(found)" in source
    assert "meta.appendChild(pageLabel)" in source
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


def test_addition_progress_patch_is_independent_from_history() -> None:
    sample = "before\n" + _ADDITION_PROGRESS_MARKER + "\n" + _ADDITION_RENDER_MARKER + "after\n"
    patched = _patch_addition_progress(sample)
    for identifier in (
        "addition_progress_block",
        "addition_progress_percent",
        "addition_progress_label",
        "addition_progress_bar",
        "addition_now",
    ):
        assert f'id="{identifier}"' in patched
    assert "additionProgressTotal" in patched
    assert "additionProgressProcessed" in patched
    assert "aria-valuenow" in patched
    assert "addition_history" not in patched
    assert "__crapScraperSyncAdditionHistoryTabs" not in patched
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
    assert "cloneNode" not in source


def test_history_is_not_touched_by_late_alignment_layers() -> None:
    for path in (
        "app/static/operational_ui_final_alignment.js",
        "app/static/operational_ui_consistency_v4.js",
        "app/static/operational_ui_card_size_parity_v6.js",
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "updates_history" not in source
        assert "addition_history" not in source
        assert "standardizeAdditionHistory" not in source


def test_preparation_and_queue_pagination_keep_shared_grid() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert "#tab_panel_atualizacoes .listing-pagination" in source
    assert "#tab_panel_adicoes .addition-pagination" in source
    assert "grid-template-columns:minmax(180px,1fr) auto minmax(180px,1fr)!important" in source
    for selector in (
        "#addition_preparation_accordion .addition-pagination",
        "#addition_queue_accordion .addition-pagination",
        "#updates_queue_list_controls .listing-pagination",
    ):
        assert selector in source


def test_logs_have_consistent_left_aligned_titles_without_loading_meta() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert "normalizeAccordionsAndLogs" in source
    assert "cs-op-summary-left" in source
    assert '"Log técnico da atualização"' in source
    assert '"Log técnico das adições"' in source
    assert "addition_technical_summary" in source


def test_lazy_addition_alignment_retries_are_finite_and_event_driven() -> None:
    source = Path("app/static/operational_ui_final_alignment.js").read_text(encoding="utf-8")
    assert "6000" in source
    assert 'document.addEventListener("click"' in source
    assert '"#addition_preparation_accordion > summary"' in source
    assert "setInterval(" not in source
    assert "MutationObserver" not in source


def test_standardization_policy_injects_shared_history_assets() -> None:
    source = Path("app/panel_layout_standardization_policy.py").read_text(encoding="utf-8")
    assert "operational_history_shared.js" in source
    assert "operational_history_shared.css" in source
    assert "install_operational_history_shared_policy" in source
    assert "_patch_addition_progress" in source


def test_process_header_keeps_credits_after_button() -> None:
    source = Path("app/static/processes_header_position.js").read_text(encoding="utf-8")
    assert "cs_processes_header_group" in source
    assert "group.appendChild(button)" in source
    assert "group.appendChild(credits)" in source
    assert "display:inline-flex" in source


def test_standardization_policy_is_installed_after_stability_fixes() -> None:
    source = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")
    assert "install_panel_layout_standardization_policy" in source
    assert source.index("install_local_ui_resilience_policy()") < source.index("install_panel_layout_standardization_policy()")
    assert "install_addition_loading_render_fix_policy" not in source
