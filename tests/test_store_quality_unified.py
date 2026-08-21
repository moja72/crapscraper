from __future__ import annotations

from pathlib import Path

from app.store_quality_unified_policy import _plain_short_description, products_missing_custom_fields


class FakeWoo:
    def __init__(self, products):
        self.products = list(products)
        self.calls = []
        self.direct_calls = []

    def list_products(self, *, page=1, per_page=100, **filters):
        self.calls.append({"page": page, "per_page": per_page, **filters})
        query = str(filters.get("search", "") or "").casefold()
        rows = self.products
        if query:
            rows = [row for row in rows if query in str(row.get("name", "")).casefold()]
        start = (page - 1) * per_page
        return rows[start:start + per_page]

    def get_product_fresh(self, product_id):
        self.direct_calls.append(product_id)
        return next(row for row in self.products if int(row.get("id") or 0) == int(product_id))


def product(product_id, name, *, version="", developer="", official="", description=""):
    return {
        "id": product_id,
        "name": name,
        "type": "variable",
        "status": "publish",
        "permalink": f"https://plugintema.com.br/produto/{product_id}/",
        "categories": [{"name": "Plugins"}, {"name": "Elementor"}],
        "variations": [1001, 1002],
        "short_description": description,
        "meta_data": [
            {"key": "pt_versao", "value": version},
            {"key": "desenvolvedor", "value": developer},
            {"key": "site_oficial", "value": official},
        ],
    }


def test_numeric_query_uses_direct_product_lookup_and_shows_complete_product():
    woo = FakeWoo([
        product(92038, "Produto completo", version="1.2.3", developer="Acme", official="https://example.com", description="Descrição pronta"),
        product(92039, "Outro"),
    ])

    rows = products_missing_custom_fields(
        woo,
        query="92038",
        selected_fields=["version", "developer", "official"],
    )

    assert [row["product_id"] for row in rows] == [92038]
    assert rows[0]["missing_fields"] == []
    assert woo.direct_calls == [92038]
    assert woo.calls == []


def test_name_query_uses_woocommerce_search_instead_of_full_catalog_scan():
    woo = FakeWoo([
        product(10, "Elementor Addon"),
        product(11, "Outro plugin"),
    ])

    rows = products_missing_custom_fields(woo, query="Elementor", selected_fields=["version"])

    assert [row["product_id"] for row in rows] == [10]
    assert woo.calls[0]["search"] == "Elementor"
    assert len(woo.calls) == 1


def test_short_description_plain_text_handles_html_and_empty_markup():
    assert _plain_short_description({"short_description": "<p>Texto &amp; detalhes</p>"}) == "Texto & detalhes"
    assert _plain_short_description({"short_description": "<p>&nbsp;</p>"}) == ""


def test_frontend_contract_unifies_description_and_collapses_price_sections():
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "store_quality_unified.js"
    ).read_text(encoding="utf-8")

    assert 'value="description" checked' in script
    assert "Breve descrição" in script
    assert "shortCard?.remove()" in script
    assert "store-price-inner-accordion" in script
    assert 'details.open = false' in script
    assert "Preços de Plugins e Temas" in script
    assert "Preços de pacotes" in script
    assert "Preços dos planos" in script
    assert "Sem pendências" in script
