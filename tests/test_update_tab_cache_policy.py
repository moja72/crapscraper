from __future__ import annotations

import app.update_operational_ui_policy as policy


def _decision() -> dict[str, object]:
    return {
        "comparison_item_id": "comparison_1",
        "woo_product_id": 123,
        "site_name": "Produto Teste",
        "site_version": "1.0.0",
        "source_version": "1.1.0",
        "source_product_url": "https://example.test/produto",
        "source_official_url": "https://developer.test/produto",
        "decision": "approve_update",
        "relationship_state": "safe_auto",
        "queue_type": "update",
    }


def test_materialization_reuses_persistent_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_CACHE_PATH", tmp_path / "update_tab_cache.json")
    monkeypatch.setattr(policy, "_CACHE_STATE", {})
    monkeypatch.setattr(policy, "list_approved_updates", lambda: [_decision()])

    calls: list[list[dict[str, object]]] = []
    cached_jobs: list[dict[str, object]] = []

    def materialize(rows):
        calls.append([dict(row) for row in rows])
        return [{"job_id": "job-1", "queue_name": "default", "queue_type": "update"}]

    monkeypatch.setattr(policy, "_BASE_MATERIALIZE", materialize)
    monkeypatch.setattr(policy, "_current_update_jobs", lambda: list(cached_jobs))

    rows = [{"comparison_item_id": "comparison_1", "site_name": "Produto Teste"}]
    first = policy._read_update_jobs(rows)
    cached_jobs[:] = first
    second = policy._read_update_jobs(rows)

    assert first == second
    assert len(calls) == 1
    assert policy._CACHE_STATE["materialize_signature"]
    assert policy._CACHE_STATE["materialize_job_ids"] == ["job-1"]


def test_prerequisites_are_served_from_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_CACHE_PATH", tmp_path / "update_tab_cache.json")
    monkeypatch.setattr(policy, "_CACHE_STATE", {})

    calls = []

    def prerequisites(*, check_ssh_connection=False, app=None):
        calls.append((check_ssh_connection, app))
        return {"woocommerce": {"ok": True}, "ssh_read": {"ok": True}}

    monkeypatch.setattr(policy, "_BASE_PREREQUISITES", prerequisites)

    first = policy._cached_update_prerequisites(app="app")
    second = policy._cached_update_prerequisites(app="app")

    assert first == second
    assert len(calls) == 1
    assert policy._CACHE_STATE["prerequisites"]["woocommerce"]["ok"] is True
