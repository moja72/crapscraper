from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from app.current_app_recovery import (
    _catalog,
    _decorate_update_item,
    _product_price_apply,
    _product_price_preview,
)


class Gateway:
    def __init__(self):
        self.products = {
            10: {
                "id": 10,
                "name": "Alpha Plugin",
                "type": "variable",
                "categories": [{"name": "Plugins"}],
                "regular_price": "",
                "sale_price": "",
            },
            20: {
                "id": 20,
                "name": "Beta Theme",
                "type": "simple",
                "categories": [{"name": "Temas"}],
                "regular_price": "120.00",
                "sale_price": "99.00",
            },
            30: {
                "id": 30,
                "name": "Pack Ignorado",
                "type": "bundle",
                "categories": [{"name": "Packs"}],
                "regular_price": "300.00",
                "sale_price": "",
            },
        }
        self.variation_rows = {
            10: [
                {"id": 101, "name": "Anual", "attributes": [{"option": "Anual"}], "regular_price": "100.00", "sale_price": "80.00"},
                {"id": 102, "name": "Vitalícia", "attributes": [{"option": "Vitalícia"}], "regular_price": "200.00", "sale_price": "160.00"},
            ]
        }
        self.variation_writes = []
        self.product_writes = []

    def product(self, product_id):
        return self.products[int(product_id)]

    def update_variations(self, product_id, updates):
        self.variation_writes.append((int(product_id), list(updates)))
        current = {row["id"]: row for row in self.variation_rows[int(product_id)]}
        for update in updates:
            current[int(update["id"])]["regular_price"] = update["regular_price"]
            current[int(update["id"])]["sale_price"] = update["sale_price"]
        return list(updates)

    def update_product_price(self, product_id, regular, sale):
        self.product_writes.append((int(product_id), regular, sale))
        product = self.products[int(product_id)]
        product["regular_price"] = regular
        product["sale_price"] = sale
        return product


class BundleService:
    def list(self, products, group):
        return [{"price_group": group, "product_id": int(row["id"])} for row in products if row.get("type") == "bundle"] if group == "pack" else []


class Repository:
    def __init__(self):
        self.runs = []
        self.attempts = []

    def pricing_run(self, status, payload, result):
        self.runs.append((status, dict(payload), dict(result)))

    def history(self, _job_id):
        return list(self.attempts)


class Service:
    def __init__(self):
        self.gateway = Gateway()
        self.bundles_service = BundleService()
        self.repository = Repository()
        self.write_enabled = True
        self.lock = threading.RLock()
        self._variation_cache = {}
        self._variation_cached_at = {}
        self._cached_at = 1.0

    def _products(self, refresh=False):
        return list(self.gateway.products.values())

    def _variations(self, product_id):
        return list(self.gateway.variation_rows.get(int(product_id), []))


def test_catalog_uses_real_products_search_type_and_pagination():
    service = Service()
    payload = _catalog(service, {"query": "beta", "type": "theme", "page": 1, "page_size": 10})
    assert payload["individual"]["total"] == 1
    assert payload["individual"]["items"][0]["product_id"] == 20
    assert payload["individual"]["available_products"] == {"plugin": 1, "theme": 1}
    assert payload["packs"]["items"][0]["product_id"] == 30


def test_variable_product_price_preview_and_apply_update_only_requested_variation():
    service = Service()
    payload = {
        "product_id": 10,
        "variations": [{"id": 101, "regular_price": "110", "sale_price": "85"}],
        "confirmation": "ALTERAR PREÇO",
    }
    preview = _product_price_preview(service, payload)
    assert preview["status"] == "change"
    assert preview["variation_changes"] == [{
        "id": 101,
        "name": "Anual",
        "regular_price": "110.00",
        "sale_price": "85.00",
        "status": "change",
    }]

    result = _product_price_apply(service, payload)
    assert result["updated"] is True
    assert result["changed"] == 1
    assert service.gateway.variation_writes == [(10, [{"id": 101, "regular_price": "110.00", "sale_price": "85.00"}])]
    assert service.repository.runs[-1][0] == "success"


def test_simple_theme_price_apply_updates_direct_product_price():
    service = Service()
    payload = {"product_id": 20, "regular_price": "130", "sale_price": "105", "confirmation": "ALTERAR PRECO"}
    result = _product_price_apply(service, payload)
    assert result["updated"] is True
    assert service.gateway.product_writes == [(20, "130.00", "105.00")]


def test_price_apply_requires_write_gate_and_confirmation():
    service = Service()
    service.write_enabled = False
    with pytest.raises(PermissionError):
        _product_price_apply(service, {"product_id": 20, "regular_price": "130", "sale_price": "105", "confirmation": "ALTERAR PRECO"})
    service.write_enabled = True
    with pytest.raises(ValueError, match="ALTERAR PREÇO"):
        _product_price_apply(service, {"product_id": 20, "regular_price": "130", "sale_price": "105", "confirmation": "SIM"})


def test_update_metrics_count_only_real_completed_updates():
    service = Service()
    service.repository.attempts = [
        {"result": "success", "finished_at": "2026-09-01T10:00:00+00:00", "stages": [{"stage": "completed"}]},
        {"result": "success", "finished_at": "2026-09-02T10:00:00+00:00", "stages": [{"stage": "already_current"}]},
        {"result": "error", "finished_at": "2026-09-03T10:00:00+00:00", "stages": [{"stage": "completed"}]},
        {"result": "success", "finished_at": "2026-09-04T10:00:00+00:00", "stages": [{"stage": "completed"}]},
    ]
    item = _decorate_update_item(service, {
        "job_id": "upd-1",
        "state": "success",
        "finished_at": "2026-09-04T10:00:00+00:00",
        "updated_at": "2026-09-04T10:00:00+00:00",
    })
    assert item["updates_count"] == 2
    assert item["last_updated_at"] == "2026-09-04T10:00:00+00:00"
    assert item["status_at"] == "2026-09-04T10:00:00+00:00"
