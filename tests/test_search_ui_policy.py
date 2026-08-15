from pathlib import Path


def test_search_ui_policy_injects_unified_script():
    root = Path(__file__).resolve().parents[1]
    policy = (root / "app" / "search_ui_policy.py").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "unified_search_ui.js").read_text(encoding="utf-8")
    assert "data-unified-search-ui" in policy
    assert "PAGE_SIZES = [5, 10, 25, 50, 100, 250]" in script
    assert "ss-page-jump" in script
    for token in (
        "comparison_page_size",
        "updates_page_size",
        "updates_queue_page_size",
        "updates_history_page_size",
        "plugintema_manage_page_size",
        "catalog_preview_page_size",
    ):
        assert token in script
