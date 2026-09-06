from __future__ import annotations

from app.comparison import decisions
from app import update_completion_and_retry_runtime as runtime


def test_version_drift_is_recoverable_for_existing_error():
    job = {
        "state": "error",
        "error": {
            "code": "execution_failed",
            "message": "Versão da fonte divergiu da aprovação: 10.0.13 != 10.0.11",
            "recoverable": False,
        },
    }
    recovered = runtime._recoverable_job(job)
    assert recovered["error"]["recoverable"] is True
    assert recovered["error"]["code"] == "source_version_drift"
    assert job["error"]["recoverable"] is False


def test_unrelated_nonrecoverable_error_stays_blocked():
    job = {
        "state": "error",
        "error": {"code": "execution_failed", "message": "Configuração inválida", "recoverable": False},
    }
    assert runtime._recoverable_job(job) == job


def test_completed_update_consumes_operational_approval(tmp_path, monkeypatch):
    database = tmp_path / "decisions.sqlite3"
    monkeypatch.setenv("SCRAPER_COMPARISON_DECISIONS_DB_PATH", str(database))
    decisions.save_decision(
        "cmp-1",
        "approve_update",
        site_id="101",
        site_name="Produto",
        source_name="UltraPackV2",
        status="update_available",
        recommended_action="review_and_approve_update",
        site_version="1.0",
        source_version="1.1",
        source_product_url="https://example.test/item",
    )

    assert runtime._mark_decision_updated({"comparison_item_id": "cmp-1", "source_version": "1.1"}) is True
    saved = decisions.get_decision("cmp-1")
    assert saved["decision"] == "approve_update"
    assert saved["decision_label"] == "Atualizado"
    assert saved["status"] == "updated"
    assert saved["queue_type"] == ""
    assert saved["recommended_action"] == "no_action"
    assert saved["site_version"] == "1.1"
    assert runtime._list_approved_updates() == []


def test_completed_overlay_does_not_hide_newer_source(monkeypatch):
    runtime._ORIGINAL_BUILD_FULL_COMPARISON = lambda *_args: {
        "rows": [{
            "comparison_item_id": "cmp-1",
            "status": "update_available",
            "status_label": "Atualização disponível",
            "source_version": "1.2",
            "site_version": "1.1",
        }],
        "status_labels": {"update_available": "Atualização disponível", "updated": "Atualizado"},
        "counts": {"update_available": 1, "updated": 0},
    }
    monkeypatch.setattr(
        runtime.decisions,
        "get_decisions_map",
        lambda _ids: {"cmp-1": {"status": "updated", "source_version": "1.1"}},
    )
    payload = runtime._build_full_comparison("source.csv", "site.csv")
    assert payload["rows"][0]["status"] == "update_available"


def test_completed_overlay_projects_updated_until_catalog_catches_up(monkeypatch):
    runtime._ORIGINAL_BUILD_FULL_COMPARISON = lambda *_args: {
        "rows": [{
            "comparison_item_id": "cmp-1",
            "status": "update_available",
            "status_label": "Atualização disponível",
            "source_version": "1.1",
            "site_version": "1.0",
        }],
        "status_labels": {"update_available": "Atualização disponível", "updated": "Atualizado"},
        "counts": {"update_available": 1, "updated": 0},
    }
    monkeypatch.setattr(
        runtime.decisions,
        "get_decisions_map",
        lambda _ids: {"cmp-1": {"status": "updated", "source_version": "1.1"}},
    )
    payload = runtime._build_full_comparison("source.csv", "site.csv")
    row = payload["rows"][0]
    assert row["status"] == "updated"
    assert row["status_label"] == "Atualizado"
    assert row["decision_label"] == "Atualizado"
    assert row["site_version"] == "1.1"
    assert payload["counts"]["updated"] == 1
    assert payload["counts"]["update_available"] == 0
