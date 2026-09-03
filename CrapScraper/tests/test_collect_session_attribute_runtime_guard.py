from app.collection.engine import CollectionEngine
from app.collection.legacy_core import engine as legacy_engine


def test_collection_engine_injects_session_attribute_into_legacy_function_globals(monkeypatch):
    legacy_engine.__dict__.pop("session_attribute", None)
    legacy_engine.execute_flow_async.__globals__.pop("session_attribute", None)
    legacy_engine.execute_flow.__globals__.pop("session_attribute", None)

    CollectionEngine()

    assert legacy_engine.session_attribute == "ultrapack_http_session"
    assert legacy_engine.execute_flow_async.__globals__["session_attribute"] == "ultrapack_http_session"
    assert legacy_engine.execute_flow.__globals__["session_attribute"] == "ultrapack_http_session"
