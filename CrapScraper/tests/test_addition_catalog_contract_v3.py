from __future__ import annotations

from app.additions import catalog_taxonomy_runtime as taxonomy
from app.additions import product_content_contract_runtime as content


def _job(kind: str):
    return {
        "job_id": "job-1",
        "product_name": "Example Product",
        "kind": kind,
        "source_version": "1.0.0",
        "source_url": "https://example.test/product",
        "developer": "Example Dev",
        "official_url": "https://example.test/official",
    }


def test_plugin_uses_only_existing_plugin_category_and_no_tags():
    job = taxonomy.canonicalize_job_taxonomy(_job("plugin"))
    assert job["categories"] == ["Plugin"]
    assert job["category_ids"] == [504]
    assert job["tags"] == []


def test_theme_uses_only_existing_theme_category_and_no_tags():
    job = taxonomy.canonicalize_job_taxonomy(_job("theme"))
    assert job["categories"] == ["Tema"]
    assert job["category_ids"] == [525]
    assert job["tags"] == []


def test_prompt_forbids_lists_and_tags():
    prompt = content.strict_prompt(_job("plugin"))
    assert 'categories deve ser EXATAMENTE ["Plugin"]' in prompt
    assert 'tags deve ser EXATAMENTE []' in prompt
    assert "não use listas" in prompt.casefold()
    assert "<ul>" not in prompt
    assert "<li>" not in prompt


def test_normalize_removes_lists_from_content_and_forces_taxonomy():
    job = _job("theme")
    result = content.normalize_catalog_result(
        job,
        {
            "product_name": "Example Product",
            "short_description": "Uma descrição comercial em texto corrido.",
            "content": "<p>Introdução.</p><h2>Recursos</h2><ul><li>Item A</li><li>Item B</li></ul><p>Final.</p>",
            "categories": ["Plugins", "SEO", "Tema"],
            "tags": ["x", "y"],
        },
    )
    assert result["categories"] == ["Tema"]
    assert result["tags"] == []
    assert "<ul" not in result["content"].casefold()
    assert "<li" not in result["content"].casefold()
    assert "<h2" not in result["content"].casefold()
