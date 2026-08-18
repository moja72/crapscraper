from __future__ import annotations

from app.store_pack_variation_policy import (
    _list_store_plan_products,
    _patched_update_store_pack_price,
    is_plan_product,
)


class FakeWoo:
    def __init__(self) -> None:
        self.products = {
            200: {
                "id": 200,
                "name": "Plano Premium",
                "type": "variable-subscription",
                "status": "publish",
                "categories": [{"id": 9, "name": "Planos"}],
                "regular_price": "",
                "sale_price": "",
                "price": "",
            },
            201: {
                "id": 201,
                "name": "Plugin comum",
                "type": "variable",
                "status": "publish",
                "categories": [{"id": 5, "name": "Plugins"}],
                "regular_price": "",
                "sale_price": "",
                "price": "",
            },
        }
        self.variation = {
            "id": 220,
            "name": "Plano Premium - Mensal",
            "sku": "premium-mensal",
            "attributes": [{"name": "Período", "option": "Mensal"}],
            "regular_price": "29.90",
            "sale_price": "19.90",
            "price": "19.90",
        }
        self.updated_variations: list[dict] = []
        self.updated_products: list[tuple[int, str, str]] = []

    def list_products(self, *, page: int = 1, per_page: int = 100, **_filters):
        return list(self.products.values()) if page == 1 else []

    def get_product(self, product_id: int):
        return self.products[product_id]

    def get_variation(self, product_id: int, variation_id: int):
        assert product_id == 200
        assert variation_id == 220
        return dict(self.variation)

    def update_variations_prices(self, product_id: int, updates: list[dict], *, authorized: bool = False):
        assert authorized is True
        assert product_id == 200
        self.updated_variations = list(updates)
        return [{**self.variation, **updates[0]}]

    def update_product_prices(self, product_id: int, regular: str, sale: str, *, authorized: bool = False):
        assert authorized is True
        self.updated_products.append((product_id, regular, sale))
        return {**self.products[product_id], "regular_price": regular, "sale_price": sale, "price": sale or regular}


def test_plan_detection_uses_category_type_or_name_without_confusing_plugins() -> None:
    woo = FakeWoo()
    assert is_plan_product(woo.products[200]) is True
    assert is_plan_product(woo.products[201]) is False


def test_plan_listing_returns_only_recognized_plan_products() -> None:
    rows = _list_store_plan_products(FakeWoo())
    assert [row["product_id"] for row in rows] == [200]
    assert rows[0]["pricing_group"] == "plan"


def test_plan_variation_price_update_reuses_controlled_price_writer() -> None:
    woo = FakeWoo()
    result = _patched_update_store_pack_price(
        woo,
        {
            "product_id": 200,
            "variation_id": 220,
            "regular_price": "39,90",
            "sale_price": "24,90",
        },
    )
    assert result["ok"] is True
    assert result["product"]["pricing_group"] == "plan"
    assert result["product"]["variation"] == "Mensal"
    assert woo.updated_variations == [{"id": 220, "regular_price": "39.90", "sale_price": "24.90"}]
