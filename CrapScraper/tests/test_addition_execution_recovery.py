from __future__ import annotations

import json
from pathlib import Path

import requests

from app.addition_execution_recovery import (
    _reset_obsolete_errors,
    _slug,
    install_addition_execution_recovery,
)
from app.additions.repository import AdditionRepository
from app.additions.source import ProductResearchService
from app.additions.wordpress import AdditionStoreGateway


def test_slug_avoids_raw_search_query_characters():
    assert _slug("1Page - Masonry WordPress News / interesting links") == "1page-masonry-wordpress-news-interesting-links"


def test_known_legacy_addition_error_is_reopened(tmp_path: Path):
    repo = AdditionRepository(tmp_path)
    approval = {
        "comparison_item_id": "legacy-openai",
        "source_name": "UltraPackV2",
        "source_version": "1.0",
        "source_product_url": "https://www.ultrapackv2.com/item/demo/",
    }
    repo.materialize([approval])
    job_id = repo.job_id("legacy-openai")
    with repo.connection() as db:
        db.execute(
            "UPDATE addition_jobs SET public_state='error',stage='generating_description',current_error=? WHERE job_id=?",
            (json.dumps({"message": "OPENAI_API_KEY não configurada para o ChatGPT"}), job_id),
        )
    assert _reset_obsolete_errors(repo) == 1
    job = repo.get(job_id)
    assert job["state"] == "ready"
    assert job["stage"] == "prepared"
    assert job["error"] is None


def test_reconcile_uses_slug_and_treats_waf_403_as_no_prior_job(monkeypatch):
    install_addition_execution_recovery()
    gateway = AdditionStoreGateway(session=object())
    calls = []

    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError("403 Client Error", response=response)

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        raise error

    monkeypatch.setattr(gateway, "_wc", wc)
    result = gateway.reconcile({
        "job_id": "add-123",
        "product_name": "1Page - Masonry WordPress News / interesting links",
        "woo_product_id": 0,
    })
    assert result == 0
    assert calls[0][2]["params"] == {
        "slug": "1page-masonry-wordpress-news-interesting-links",
        "per_page": 100,
    }


def test_missing_developer_becomes_explicit_review_marker(monkeypatch):
    install_addition_execution_recovery()
    service = ProductResearchService(session=object())
    monkeypatch.setattr(
        ProductResearchService,
        "resolve",
        lambda self, job: {"official_url": "https://developer.example/product", "developer": "Não identificado"},
    )
    result = service.resolve({"product_name": "Demo"})
    assert result["developer"] == "Não identificado"
