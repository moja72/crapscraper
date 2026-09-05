from __future__ import annotations

from pathlib import Path

from app import addition_decision_sync
from app import comparison_live_reconciliation as live
from app.additions.repository import AdditionRepository


class FakeWoo:
    def __init__(self, products):
        self._products = list(products)

    def products(self, **_filters):
        return list(self._products)


def _product(product_id=123, name="123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme"):
    return {
        "id": product_id,
        "name": name,
        "slug": "123-medicine",
        "status": "publish",
        "type": "variable",
        "permalink": "https://plugintema.com.br/produto/123-medicine/",
        "categories": [{"name": "Temas"}],
        "meta_data": [
            {"key": "pt_versao", "value": "1.5.1"},
            {"key": "site_oficial", "value": "https://themeforest.net/item/123-medicine/123"},
        ],
    }


def _new_source_row():
    name = "123 Medicine - Pharmacy Shop & Hospital / Medical / Health Service Theme"
    return {
        "status": "new_source",
        "status_label": "Novo no Ultrapack",
        "comparison_item_id": "comparison-stale",
        "decision": "approve_new_product",
        "decision_label": "Aprovar cadastro novo",
        "source_name": name,
        "source_version": "1.5.2",
        "source_product_url": "https://www.ultrapackv2.com/item/123-medicine/",
        "source_official_url": "https://themeforest.net/item/123-medicine/123",
        "source_category": "theme",
    }


def test_new_source_row_is_reconciled_against_live_woocommerce(monkeypatch):
    reset = []
    monkeypatch.setattr(live.decisions, "reset_decision", lambda item_id, operator="": reset.append((item_id, operator)) or {})
    monkeypatch.setattr(live.decisions, "get_decisions_map", lambda _ids: {})

    resolved = live.reconcile_row(_new_source_row(), FakeWoo([_product()]))

    assert resolved["live_reconciled"] is True
    assert resolved["catalog_snapshot_stale"] is True
    assert resolved["site_id"] == "123"
    assert resolved["site_name"].startswith("123 Medicine")
    assert resolved["site_version"] == "1.5.1"
    assert resolved["source_version"] == "1.5.2"
    assert resolved["status"] == "update_available"
    assert resolved["decision"] == "pending"
    assert reset and reset[0][0] == "comparison-stale"


def test_live_reconciliation_requires_unique_exact_match(monkeypatch):
    monkeypatch.setattr(live.decisions, "get_decisions_map", lambda _ids: {})
    row = _new_source_row()
    duplicate = _product(124)
    result = live.reconcile_row(row, FakeWoo([_product(), duplicate]))
    assert result["status"] == "new_source"
    assert not result.get("live_reconciled")


def _approval(version="1.0", url="https://www.ultrapackv2.com/item/demo/"):
    return {
        "comparison_item_id": "new-demo-1",
        "source_name": "UltraPackV2",
        "source_provider_name": "UltraPackV2",
        "source_version": version,
        "source_product_url": url,
        "source_official_url": "https://example.com/demo",
        "source_product_id": "demo",
        "product_name": "Demo Plugin",
        "kind": "plugin",
    }


def test_addition_materialize_updates_existing_prepared_job_and_removes_revoked(tmp_path: Path):
    addition_decision_sync._patch_repository_materialize()
    repository = AdditionRepository(tmp_path, database_path=tmp_path / "additions.sqlite3")

    first = repository.materialize([_approval("1.0")])
    assert first["created"] == 1
    item = repository.list(page_size=10)["items"][0]
    assert item["source_version"] == "1.0"

    second = repository.materialize([_approval("1.1", "https://www.ultrapackv2.com/item/demo-v2/")])
    item = repository.list(page_size=10)["items"][0]
    assert second["updated"] == 1
    assert item["source_version"] == "1.1"
    assert item["source_url"].endswith("demo-v2/")
    assert item["state"] == "ready"
    assert item["stage"] == "prepared"

    removed = repository.materialize([])
    assert removed["removed"] == 1
    assert repository.count() == 0
