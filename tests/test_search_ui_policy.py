from pathlib import Path


def test_unified_search_ui_assets_exist_and_include_page_jump():
    root = Path(__file__).resolve().parents[1]
    script = (root / "app" / "static" / "unified_search_ui.js").read_text(encoding="utf-8")
    policy = (root / "app" / "search_ui_policy.py").read_text(encoding="utf-8")
    assert "data-unified-search-ui" in policy
    assert "PAGE_SIZE_VALUES = [5, 10, 25, 50, 100, 250]" in script
    assert "u-page-jump" in script
    assert "comparison_results_card" in script
    assert "updates_history_search" in script
    assert "updates_queue_search" in script
