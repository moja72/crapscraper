from pathlib import Path


def test_store_monitor_toggle_uses_stable_wordpress_monitor_ids():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "store_manual_monitor_control.js").read_text(encoding="utf-8")

    assert 'getElementById("wp_manual_monitor")' in source
    assert 'getElementById("wp_manual_monitor_title")' in source
    assert 'role="switch"' in source
    assert 'aria-checked="false"' in source
    assert 'card.insertBefore(root, grid)' in source
