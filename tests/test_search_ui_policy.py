from pathlib import Path


def test_search_ui_policy_injects_unified_script():
    root = Path(__file__).resolve().parents[1]
    policy = (root / "app" / "search_ui_policy.py").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "unified_search_ui.js").read_text(encoding="utf-8")

    assert "data-unified-search-ui" in policy
    assert "_patch_panel_javascript" in policy
    assert "[5, 10, 25, 50, 100, 250]" in policy
    assert "window.__crapscraperPagination" in policy

    assert "PAGE_SIZES = [5, 10, 25, 50, 100, 250]" in script
    assert "cs-page-jump" in script
    assert "listing-pagination" in script
    assert "listing-meta-row" in script
    assert "updates-list-controls" in script
    assert "updates-history-toolbar" in script

    for token in (
        "comparison_page_size",
        "updates_page_size",
        "updates_queue_page_size",
        "updates_history_page_size",
        "plugintema_manage_page_size",
        "catalog_preview_page_size",
    ):
        assert token in script

    for setter in (
        "comparison",
        "updatesWaiting",
        "updatesQueue",
        "updatesHistory",
        "pluginTemaManager",
        "catalogPreview",
    ):
        assert setter in policy
