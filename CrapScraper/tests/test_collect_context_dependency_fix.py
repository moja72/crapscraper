from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
FIX_JS = (ROOT / "app" / "static" / "js" / "collect-context-dependency-fix.js").read_text(encoding="utf-8")


def test_dependency_fix_loads_before_collect_handler():
    fix_import = 'import "./collect-context-dependency-fix.js";'
    collect_import = 'import "./collect.js";'
    assert fix_import in APP_JS
    assert APP_JS.index(fix_import) < APP_JS.index(collect_import)


def test_site_change_normalizes_type_and_account_before_context_post():
    assert '#collect-site,#collect-type' in FIX_JS
    assert 'event.stopImmediatePropagation()' in FIX_JS
    assert 'siteRow.item_types' in FIX_JS
    assert 'item.sites||[]' in FIX_JS
    assert 'item.item_types||[]' in FIX_JS
    assert '#collect-account' in FIX_JS
    assert 'dispatchEvent(new Event("change",{bubbles:true}))' in FIX_JS


def test_stale_async_site_changes_do_not_override_latest_selection():
    assert 'changeVersion' in FIX_JS
    assert 'if(version!==changeVersion)return;' in FIX_JS
