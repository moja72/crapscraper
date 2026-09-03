from pathlib import Path

import app.collection.service as collection_service
from app.collection.service import CollectionService


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


def test_server_normalizes_cross_site_type_and_account(monkeypatch):
    monkeypatch.setattr(
        collection_service,
        "registry_payload",
        lambda: {
            "sites": [
                {"key": "ultrapackv2", "item_types": ["plugin", "theme"]},
                {"key": "plugintheme", "item_types": ["plugin_theme"]},
            ],
            "item_types": [
                {"key": "plugin", "label": "Plugins"},
                {"key": "theme", "label": "Temas"},
                {"key": "plugin_theme", "label": "Plugins e Temas"},
            ],
            "accounts": [
                {"key": "bernardes", "sites": ["ultrapackv2"], "item_types": ["plugin", "theme"]},
                {"key": "coproducao", "sites": ["plugintheme"], "item_types": ["plugin_theme"]},
            ],
        },
    )
    normalized = CollectionService._normalize_context_dependencies(
        {
            "site_key": "plugintheme",
            "item_type_key": "theme",
            "account_key": "bernardes",
            "slot_name": "default",
        }
    )
    assert normalized == {
        "site_key": "plugintheme",
        "item_type_key": "plugin_theme",
        "account_key": "coproducao",
        "slot_name": "default",
    }
