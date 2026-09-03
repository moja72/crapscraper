from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLLECTION_ENGINE = (ROOT / "app" / "collection" / "engine.py").read_text(encoding="utf-8")
LEGACY_ENGINE = (ROOT / "app" / "collection" / "legacy_core" / "engine.py").read_text(encoding="utf-8")


def test_ultrapack_authenticated_session_attribute_is_initialized_before_manager():
    assignment = 'legacy_engine.session_attribute = "ultrapack_http_session"'
    manager_import = "from app.collection.legacy_core.app import ScraperRunManager"

    assert assignment in COLLECTION_ENGINE
    assert manager_import in COLLECTION_ENGINE
    assert COLLECTION_ENGINE.index(assignment) < COLLECTION_ENGINE.index(manager_import)


def test_legacy_flow_publishes_session_using_compatibility_attribute():
    assert 'if resolved_context.site_key == "ultrapackv2":' in LEGACY_ENGINE
    assert "setattr(app, session_attribute, http_session)" in LEGACY_ENGINE
    assert 'previous = getattr(app, "ultrapack_http_session", None)' in LEGACY_ENGINE
