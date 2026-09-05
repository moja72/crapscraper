import requests

from app.additions.wordpress import AdditionStoreGateway


def forbidden():
    response = requests.Response()
    response.status_code = 403
    return requests.HTTPError("403 Client Error", response=response)


def test_term_returns_zero_when_taxonomy_endpoint_is_fully_blocked(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    calls = []

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/products/categories":
            raise forbidden()
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(gateway, "_wc", wc)
    assert gateway._term("category", "Temas") == 0
    assert [call[0] for call in calls] == ["GET", "GET"]


def test_create_parent_skips_blocked_taxonomy_and_preserves_names(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    sent = {}

    def wc(method, path, **kwargs):
        if path in {"/products/categories", "/products/tags"}:
            raise forbidden()
        if method == "POST" and path == "/products":
            sent.update(kwargs["json"])
            return {"id": 501, "images": [{"id": 91}]}
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(gateway, "_wc", wc)
    job = {
        "product_name": "Produto Teste",
        "kind": "theme",
        "content": "Conteúdo",
        "short_description": "Breve",
        "categories": ["Temas", "Agência"],
        "tags": ["Agency"],
        "source_version": "1.2.3",
        "official_url": "https://example.com",
        "developer": "Dev",
        "job_id": "job-1",
        "source_name": "UltraPackV2",
    }
    product = gateway.create_parent(job, 91, "https://plugintema.com/downloads/file.zip")
    assert product["id"] == 501
    assert sent["categories"] == []
    assert sent["tags"] == []
    meta = {item["key"]: item["value"] for item in sent["meta_data"]}
    assert meta["crapscraper_pending_categories"] == "Temas | Agência"
    assert meta["crapscraper_pending_tags"] == "Agency"
    assert meta["crapscraper_taxonomy_state"] == "deferred_waf"
