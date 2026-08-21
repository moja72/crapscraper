from __future__ import annotations

from pathlib import Path

from app.store_custom_fields_quality_policy import products_missing_custom_fields


class FakeWoo:
    def __init__(self, products):
        self.products = list(products)
        self.calls = []

    def list_products(self, *, page=1, per_page=100, **filters):
        self.calls.append({"page": page, "per_page": per_page, **filters})
        start = (page - 1) * per_page
        return self.products[start:start + per_page]


def product(product_id, name, *, version="", developer="", official=""):
    return {
        "id": product_id,
        "name": name,
        "type": "variable",
        "permalink": f"https://plugintema.com.br/produto/{product_id}/",
        "categories": [{"name": "Plugins"}],
        "meta_data": [
            {"key": "pt_versao", "value": version},
            {"key": "desenvolvedor", "value": developer},
            {"key": "site_oficial", "value": official},
        ],
    }


def test_lists_only_products_with_selected_missing_fields():
    woo = FakeWoo([
        product(1, "Completo", version="1.2.3", developer="Acme", official="https://example.com"),
        product(2, "Sem versão", developer="Acme", official="https://example.com"),
        product(3, "Sem autor e link", version="2.0.0"),
    ])

    rows = products_missing_custom_fields(woo, selected_fields=["version", "developer", "official"])

    assert [row["product_id"] for row in rows] == [3, 2]
    by_id = {row["product_id"]: row for row in rows}
    assert by_id[2]["missing_fields"] == ["version"]
    assert by_id[3]["missing_fields"] == ["developer", "official"]
    assert woo.calls[0]["status"] == "publish"
    assert "meta_data" in woo.calls[0]["_fields"]


def test_all_mode_requires_every_selected_field_to_be_missing():
    woo = FakeWoo([
        product(10, "Tem link", version="1.0.0", official="https://example.com"),
        product(11, "Só desenvolvedor", developer="Acme"),
        product(12, "Sem os dois"),
    ])

    rows = products_missing_custom_fields(
        woo,
        selected_fields=["developer", "official"],
        match_mode="all",
    )

    assert [row["product_id"] for row in rows] == [12]


def test_query_matches_product_name_or_woocommerce_id():
    woo = FakeWoo([
        product(21, "Elementor Addon"),
        product(92038, "Outro produto"),
    ])

    by_name = products_missing_custom_fields(woo, query="elementor", selected_fields=["version"])
    by_id = products_missing_custom_fields(woo, query="92038", selected_fields=["version"])

    assert [row["product_id"] for row in by_name] == [21]
    assert [row["product_id"] for row in by_id] == [92038]


def test_whitespace_metadata_is_treated_as_missing():
    woo = FakeWoo([product(30, "Espaços", version="   ", developer="\n", official="\t")])

    rows = products_missing_custom_fields(woo)

    assert rows[0]["missing_fields"] == ["version", "developer", "official"]


def test_ui_contract_uses_store_table_and_pagination():
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "store_custom_fields_quality.js"
    ).read_text(encoding="utf-8")

    assert 'class="store-data-table"' in script
    assert "[5, 10, 25, 50, 100]" in script
    assert "Sem versão" in script
    assert "Sem desenvolvedor" in script
    assert "Sem link oficial" in script
