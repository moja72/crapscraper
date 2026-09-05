import base64
import hashlib
import hmac
import json

import pytest
import requests

from app.additions.wordpress import AdditionStoreGateway


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class BridgeSession:
    def __init__(self):
        self.bridge_call = None

    def request(self, method, url, **kwargs):
        return FakeResponse(403, {"message": "Forbidden"})

    def post(self, url, **kwargs):
        self.bridge_call = (url, kwargs)
        return FakeResponse(200, {"ok": True, "data": {"id": 123, "type": "variable"}})


def configure(monkeypatch):
    monkeypatch.setenv("SCRAPER_WP_BASE_URL", "https://plugintema.com.br")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_KEY", "ck_test")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_SECRET", "cs_test")
    monkeypatch.setenv("SCRAPER_WORDPRESS_MANUAL_SECRET", "x" * 32)


def test_products_post_uses_opaque_signed_bridge_after_waf_403(monkeypatch):
    configure(monkeypatch)
    session = BridgeSession()
    gateway = AdditionStoreGateway(session=session)

    result = gateway._wc("POST", "/products", json={"name": "Produto"})

    assert result["id"] == 123
    url, kwargs = session.bridge_call
    assert url == "https://plugintema.com.br/wp-json/crapscraper/v2/bridge"
    envelope = kwargs["json"]
    assert set(envelope) == {"t", "s", "p"}
    decoded = json.loads(base64.b64decode(envelope["p"]).decode("utf-8"))
    assert decoded == {"method": "POST", "path": "/products", "params": {}, "json": {"name": "Produto"}}
    expected = hmac.new(
        ("x" * 32).encode(),
        envelope["t"].encode() + b"\n" + envelope["p"].encode(),
        hashlib.sha256,
    ).hexdigest()
    assert envelope["s"] == expected
    assert "X-CrapScraper-Signature" not in kwargs["headers"]
    assert kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")


def test_bridge_missing_secret_is_actionable(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("SCRAPER_WORDPRESS_MANUAL_SECRET", raising=False)
    gateway = AdditionStoreGateway(session=BridgeSession())
    with pytest.raises(RuntimeError, match="SCRAPER_WORDPRESS_MANUAL_SECRET"):
        gateway._wc("POST", "/products", json={"name": "Produto"})


def test_non_auth_server_error_is_not_hidden_by_bridge(monkeypatch):
    configure(monkeypatch)

    class ErrorSession(BridgeSession):
        def request(self, method, url, **kwargs):
            return FakeResponse(500, {"message": "boom"})

        def post(self, url, **kwargs):
            raise AssertionError("bridge must not run for HTTP 500")

    gateway = AdditionStoreGateway(session=ErrorSession())
    with pytest.raises(requests.HTTPError):
        gateway._wc("POST", "/products", json={"name": "Produto"})


def test_bridge_html_403_has_actionable_message(monkeypatch):
    configure(monkeypatch)

    class HtmlBlockedSession(BridgeSession):
        def post(self, url, **kwargs):
            return FakeResponse(403, payload=None, text="<!doctype html><title>403 Forbidden</title>")

    gateway = AdditionStoreGateway(session=HtmlBlockedSession())
    with pytest.raises(RuntimeError, match="Bridge CrapScraper recusou GET /products: HTTP 403"):
        gateway._wc("GET", "/products", params={"per_page": 100})
