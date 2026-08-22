from pathlib import Path


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
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert "MutationObserver" not in source
    assert "setInterval(" not in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source


def test_update_preparation_empty_state_is_deduplicated() -> None:
    source = Path("app/static/panel_layout_standardization.js").read_text(encoding="utf-8")
    assert "dedupeUpdatePreparationEmpty" in source
    assert 'seen.has(key)' in source
    assert "node.remove()" in source


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
