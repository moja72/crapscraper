from __future__ import annotations

from pathlib import Path

from app.store_custom_fields_quality_policy import products_missing_custom_fields


class FakeWoo:
    def __init__(self, products, variations=None):
        self.products = list(products)
        self.variations = dict(variations or {})
        self.calls = []
        self.variation_calls = []

    def list_products(self, *, page=1, per_page=100, **filters):
        self.calls.append({"page": page, "per_page": per_page, **filters})
        start = (page - 1) * per_page
        return self.products[start:start + per_page]

    def list_variations(self, product_id, *, per_page=100, **filters):
        self.variation_calls.append({"product_id": product_id, "per_page": per_page, **filters})
        return list(self.variations.get(product_id, []))


def product(
    product_id,
    name,
    *,
    version="",
    developer="",
    official="",
    kind="plugin",
    categories=None,
    product_type="variable",
    child_ids=(1, 2),
):
    default_categories = [{"name": "Plugins" if kind == "plugin" else "Temas"}]
    return {
        "id": product_id,
        "name": name,
        "type": product_type,
        "permalink": f"https://plugintema.com.br/produto/{product_id}/",
        "categories": categories if categories is not None else default_categories,
        "variations": list(child_ids),
        "meta_data": [
            {"key": "pt_versao", "value": version},
            {"key": "desenvolvedor", "value": developer},
            {"key": "site_oficial", "value": official},
        ],
    }


def variation(variation_id, option):
    return {
        "id": variation_id,
        "name": f"Variação {option}",
        "sku": "",
        "attributes": [{"name": "Licença", "option": option}],
    }


def test_lists_only_variable_plugin_theme_products_with_children():
    woo = FakeWoo([
        product(1, "Plugin válido"),
        product(2, "Tema válido", kind="theme"),
        product(3, "Plano", categories=[{"name": "Planos"}]),
        product(4, "Membro", categories=[{"name": "Membros"}]),
        product(5, "Plugin simples", product_type="simple"),
        product(6, "Plugin sem filhos", child_ids=()),
    ])

    rows = products_missing_custom_fields(woo, selected_fields=["version"])

    assert [row["product_id"] for row in rows] == [1, 2]
    assert {row["catalog_kind"] for row in rows} == {"plugin", "theme"}
    assert woo.calls[0]["status"] == "publish"
    assert "variations" in woo.calls[0]["_fields"]


def test_lists_only_products_with_selected_missing_fields():
    woo = FakeWoo([
        product(10, "Completo", version="1.2.3", developer="Acme", official="https://example.com"),
        product(11, "Sem versão", developer="Acme", official="https://example.com"),
        product(12, "Sem autor e link", version="2.0.0"),
    ])

    rows = products_missing_custom_fields(woo, selected_fields=["version", "developer", "official"])

    assert [row["product_id"] for row in rows] == [12, 11]
    by_id = {row["product_id"]: row for row in rows}
    assert by_id[11]["missing_fields"] == ["version"]
    assert by_id[12]["missing_fields"] == ["developer", "official"]


def test_root_category_filter_requires_only_plugin_or_theme_root():
    woo = FakeWoo([
        product(20, "Plugin só raiz", categories=[{"name": "Plugins"}]),
        product(21, "Plugin Elementor", categories=[{"name": "Plugins"}, {"name": "Elementor"}]),
        product(22, "Tema só raiz", kind="theme", categories=[{"name": "Temas"}]),
    ])

    rows = products_missing_custom_fields(woo, selected_fields=["version"], category_mode="root_only")

    assert [row["product_id"] for row in rows] == [20, 22]
    assert all(row["root_category_only"] for row in rows)


def test_nonstandard_variation_filter_finds_product_with_outlier_child():
    woo = FakeWoo(
        [product(30, "Padrão"), product(31, "Tem 6 meses")],
        {
            30: [variation(301, "1 Ano"), variation(302, "Vitalício")],
            31: [variation(311, "1 Ano"), variation(312, "6 Meses")],
        },
    )

    rows = products_missing_custom_fields(woo, selected_fields=["version"], variation_mode="nonstandard")

    assert [row["product_id"] for row in rows] == [31]
    assert rows[0]["nonstandard_variation_count"] == 1
    assert rows[0]["standard_labels"] == ["1 ano"]


def test_none_standard_filter_requires_no_annual_lifetime_or_free_child():
    woo = FakeWoo(
        [product(40, "Misturado"), product(41, "Nenhum padrão"), product(42, "Gratuito")],
        {
            40: [variation(401, "1 Ano"), variation(402, "6 Meses")],
            41: [variation(411, "6 Meses"), variation(412, "3 Meses")],
            42: [variation(421, "Gratuito")],
        },
    )

    rows = products_missing_custom_fields(woo, selected_fields=["version"], variation_mode="none_standard")

    assert [row["product_id"] for row in rows] == [41]
    assert rows[0]["standard_terms"] == []
    assert rows[0]["nonstandard_variation_count"] == 2


def test_all_mode_requires_every_selected_field_to_be_missing():
    woo = FakeWoo([
        product(50, "Tem link", version="1.0.0", official="https://example.com"),
        product(51, "Só desenvolvedor", developer="Acme"),
        product(52, "Sem os dois"),
    ])

    rows = products_missing_custom_fields(
        woo,
        selected_fields=["developer", "official"],
        match_mode="all",
    )

    assert [row["product_id"] for row in rows] == [52]


def test_query_matches_product_name_or_woocommerce_id():
    woo = FakeWoo([product(61, "Elementor Addon"), product(92038, "Outro produto")])

    by_name = products_missing_custom_fields(woo, query="elementor", selected_fields=["version"])
    by_id = products_missing_custom_fields(woo, query="92038", selected_fields=["version"])

    assert [row["product_id"] for row in by_name] == [61]
    assert [row["product_id"] for row in by_id] == [92038]


def test_whitespace_metadata_is_treated_as_missing():
    woo = FakeWoo([product(70, "Espaços", version="   ", developer="\n", official="\t")])

    rows = products_missing_custom_fields(woo)

    assert rows[0]["missing_fields"] == ["version", "developer", "official"]


def test_ui_contract_uses_store_table_pagination_and_structure_filters():
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "store_custom_fields_quality.js"
    ).read_text(encoding="utf-8")

    assert 'class="store-data-table"' in script
    assert "[5, 10, 25, 50, 100]" in script
    assert "Somente categoria raiz Plugin/Tema" in script
    assert "Com termo fora de 1 ano / Vitalício / Gratuito" in script
    assert "Sem nenhum termo 1 ano / Vitalício / Gratuito" in script
    assert "Planos, membros, packs e outros tipos são ignorados" in script
