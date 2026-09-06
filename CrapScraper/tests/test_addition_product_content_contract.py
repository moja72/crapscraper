from __future__ import annotations

from app.additions import catalog_taxonomy_runtime as taxonomy
from app.additions import product_content_contract_runtime as content_contract


def plugin_job():
    return {
        "job_id": "add-plugin",
        "product_name": "Admin Columns Pro JetEngine",
        "kind": "plugin",
        "source_version": "1.2.3",
        "source_url": "https://example.com/source",
        "official_url": "https://example.com/official",
        "developer": "Developer",
        "source_name": "UltraPackV2",
        "short_description": "x" * 400,
        "content": "<p>" + "a" * 180 + "</p><p>" + "b" * 180 + "</p>",
    }


def test_prompt_uses_elementor_pro_as_style_model_and_fixed_taxonomy():
    prompt = content_contract.strict_prompt(plugin_job())
    assert content_contract.ELEMENTOR_PRO_MODEL in prompt
    assert 'categories deve ser EXATAMENTE ["Plugin"]' in prompt
    assert "tags deve ser EXATAMENTE []" in prompt
    assert "sem copiar recursos do Elementor" in prompt


def test_result_forces_exact_product_name_one_category_and_no_tags():
    result = content_contract.normalize_catalog_result(
        plugin_job(),
        {
            "product_name": "Nome alterado pelo modelo",
            "short_description": "  descrição   com   espaços  ",
            "content": "<p>conteúdo</p>",
            "categories": ["Plugins", "WooCommerce"],
            "tags": ["WordPress", "JetEngine"],
        },
    )
    assert result["product_name"] == "Admin Columns Pro JetEngine"
    assert result["categories"] == ["Plugin"]
    assert result["tags"] == []
    assert result["short_description"] == "descrição com espaços"


def test_content_fingerprint_version_invalidates_old_cached_descriptions():
    fingerprint = content_contract.content_fingerprint(plugin_job())
    assert fingerprint.startswith("content-contract-v2|")


def test_plugin_and_theme_use_existing_plugintheme_category_ids():
    assert taxonomy.canonical_category(plugin_job()) == "Plugin"
    assert taxonomy.canonical_category_id(plugin_job()) == 504
    theme = {**plugin_job(), "kind": "theme"}
    assert taxonomy.canonical_category(theme) == "Tema"
    assert taxonomy.canonical_category_id(theme) == 525


def test_parent_payload_uses_fixed_id_and_never_tags():
    from app.additions.wordpress import AdditionStoreGateway

    taxonomy._INSTALLED = False
    taxonomy.install_catalog_taxonomy_contract()
    gateway = object.__new__(AdditionStoreGateway)
    payload = gateway._parent_payload(plugin_job(), 123, status="draft")
    assert payload["categories"] == [{"id": 504}]
    assert payload["tags"] == []
    assert payload["images"] == [{"id": 123}]
