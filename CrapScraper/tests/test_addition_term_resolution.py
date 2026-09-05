import requests

from app.additions.wordpress import AdditionStoreGateway


def test_category_lookup_uses_slug_instead_of_search(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    calls = []

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        params = kwargs.get("params") or {}
        assert "search" not in params
        if method == "GET" and params.get("slug") == "temas":
            return [{"id": 17, "name": "Temas", "slug": "temas"}]
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(gateway, "_wc", wc)
    assert gateway._term("category", "Temas") == 17
    assert calls[0][2]["params"] == {"slug": "temas", "per_page": 100}


def test_term_lookup_falls_back_to_unfiltered_page_when_slug_is_forbidden(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    calls = []

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        params = kwargs.get("params") or {}
        assert "search" not in params
        if method == "GET" and "slug" in params:
            response = requests.Response()
            response.status_code = 403
            error = requests.HTTPError("403 Client Error", response=response)
            raise error
        if method == "GET":
            return [{"id": 9, "name": "Plugins", "slug": "plugins"}]
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(gateway, "_wc", wc)
    assert gateway._term("category", "Plugins") == 9
    assert len(calls) == 2


def test_missing_tag_is_created_without_search_query(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    calls = []

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        params = kwargs.get("params") or {}
        assert "search" not in params
        if method == "GET":
            return []
        if method == "POST":
            assert kwargs["json"] == {"name": "Gallery"}
            return {"id": 44}
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(gateway, "_wc", wc)
    assert gateway._term("tag", "Gallery") == 44
