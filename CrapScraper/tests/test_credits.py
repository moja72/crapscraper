from __future__ import annotations

import requests

from app import credits


class Response:
    def __init__(self, text: str, *, url: str = "https://example.test/account", status: int = 200, payload=None):
        self.text, self.url, self.status_code, self._payload = text, url, status, payload
        self.ok = status < 400

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)

    def get(self, *_args, **_kwargs):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def test_credit_parser_preserves_real_zero() -> None:
    assert credits.extract_credit_numbers({"downloadLimit": 40, "remainingDownloads": 0}) == {"limit": 40, "remaining": 0, "used": 40}
    assert credits.extract_credit_numbers({"remainingCredits": 0}) == {"remaining": 0}
    assert credits.extract_credit_numbers("Saldo: 18 créditos") == {"remaining": 18}


def test_ultrapack_authenticated_credit_is_returned(monkeypatch) -> None:
    monkeypatch.setattr(credits, "_session", lambda _kind: (Session([Response("Créditos: 18 de 40")]), False))
    result = credits._provider_payload("ultrapackv2")
    assert result["ok"] is True and result["remaining"] == 18 and result["limit"] == 40


def test_plugintheme_authenticated_credit_uses_check_access(monkeypatch) -> None:
    product = Response('prefix "id":"12345678-1234-1234-1234-123456789012" suffix')
    access = Response("", payload={"data": {"downloadLimit": 50, "remainingDownloads": 7}})
    monkeypatch.setattr(credits, "_session", lambda _kind: (Session([product, access]), False))
    result = credits._provider_payload("plugintheme")
    assert result["ok"] is True and result["remaining"] == 7 and result["source"] == "check-access"


def test_expired_session_is_not_reported_as_zero(monkeypatch) -> None:
    login = Response('<form><input type="password">Login</form>', url="https://example.test/login")
    monkeypatch.setattr(credits, "_session", lambda _kind: (Session([login]), False))
    result = credits._provider_payload("ultrapackv2")
    assert result == {"ok": False, "status": "expired", "message": "Sessão expirada."}


def test_unreachable_service_is_unavailable_not_zero(monkeypatch, caplog) -> None:
    failures = [requests.ConnectionError("offline")] * len(credits._ULTRAPACK_ACCOUNT_URLS)
    monkeypatch.setattr(credits, "_session", lambda _kind: (Session(failures), False))
    with caplog.at_level("WARNING"):
        result = credits._provider_payload("ultrapackv2")
    assert result["ok"] is False and result["status"] == "unavailable" and "offline" not in result["message"]
    assert "Créditos UltraPackV2 indisponíveis" in caplog.text
