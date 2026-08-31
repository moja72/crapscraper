from __future__ import annotations

import threading
import time
import weakref

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


def success(site: str, account: str, amount: int) -> dict:
    return {
        "ok": True, "site_key": site, "account_key": account, "credits": amount,
        "remaining": amount, "status": "success", "updated_at": "2026-08-31T03:42:00+00:00",
        "source": "fixture", "logs": [f"Saldo localizado: {amount}."],
    }


def test_credit_parser_preserves_real_zero() -> None:
    assert credits.extract_credit_numbers({"downloadLimit": 40, "remainingDownloads": 0}) == {"limit": 40, "remaining": 0, "used": 40}
    assert credits.extract_credit_numbers({"remainingCredits": 0}) == {"remaining": 0}
    assert credits.extract_credit_numbers("Saldo: 18 créditos") == {"remaining": 18}


def test_ultrapack_uses_real_authenticated_dashboard_fields(monkeypatch) -> None:
    html = '<div class="limite-diario-topline"><span>LIMITE DIÁRIO</span> 40</div><a class="baixados-hoje-topline">DOWNLOADS HOJE 1</a>'
    monkeypatch.setattr(credits, "_session", lambda _site, _account, _url: Session([Response(html)]))
    result = credits._provider_payload("ultrapackv2", "coproducaolancamentos")
    assert result["ok"] is True and result["credits"] == 39
    assert (result["limit"], result["used"]) == (40, 1)
    assert result["source"].startswith("painel:")


def test_plugintheme_uses_structured_check_access(monkeypatch) -> None:
    product = Response('prefix "id":"12345678-1234-1234-1234-123456789012" suffix')
    access = Response("", payload={"data": {"downloadLimit": 50, "remainingDownloads": 7}})
    monkeypatch.setattr(credits, "_session", lambda _site, _account, _url: Session([product, access]))
    result = credits._provider_payload("plugintheme", "coproducaolancamentos")
    assert result["ok"] is True and result["credits"] == 7 and result["source"] == "api:check-access"


def test_expired_session_is_diagnostic_not_zero(monkeypatch) -> None:
    login = Response('<form><input type="password">Login</form>', url="https://example.test/login")
    monkeypatch.setattr(credits, "_session", lambda _site, _account, _url: Session([login]))
    result = credits._provider_payload("ultrapackv2", "account-a")
    assert result["ok"] is False and result["status"] == "expired" and result["credits"] is None
    assert "expirada" in result["message"].lower()


def test_response_without_balance_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(credits, "_session", lambda _site, _account, _url: Session([Response("Painel autenticado sem contador")]))
    result = credits._provider_payload("ultrapackv2", "account-a")
    assert result["ok"] is False and result["status"] == "unavailable" and result["credits"] is None


def test_ultrapack_rejects_incoherent_used_greater_than_limit(monkeypatch) -> None:
    html = '<div class="limite-diario-topline">40</div><a class="baixados-hoje-topline">41</a>'
    monkeypatch.setattr(credits, "_session", lambda _site, _account, _url: Session([Response(html)]))
    result = credits._provider_payload("ultrapackv2", "account-a")
    assert result["ok"] is False and result["status"] == "invalid" and result["credits"] is None


def test_refresh_changes_value_and_persists_by_site_and_account(tmp_path) -> None:
    values = iter((37, 35, 12))
    service = credits.CreditService(tmp_path, provider=lambda site, account: success(site, account, next(values)))
    assert service.refresh("ultrapackv2", "account-a")["credits"] == 37
    assert service.refresh("ultrapackv2", "account-a")["credits"] == 35
    assert service.refresh("plugintheme", "account-a")["credits"] == 12
    reloaded = credits.CreditService(tmp_path, provider=lambda *_: (_ for _ in ()).throw(AssertionError("não consultar")))
    assert reloaded.cached("ultrapackv2", "account-a")["credits"] == 35
    assert reloaded.cached("plugintheme", "account-a")["credits"] == 12


def test_failed_refresh_preserves_last_confirmed_as_stale(tmp_path) -> None:
    calls = 0
    def provider(site, account):
        nonlocal calls
        calls += 1
        if calls == 1:
            return success(site, account, 22)
        return {"ok": False, "status": "expired", "message": "Sessão expirada.", "logs": ["Sessão expirada."], "updated_at": "2026-08-31T04:00:00+00:00"}
    service = credits.CreditService(tmp_path, provider=provider)
    assert service.refresh("plugintheme", "account-a")["credits"] == 22
    stale = service.refresh("plugintheme", "account-a")
    assert stale["credits"] == 22 and stale["stale"] is True and stale["ok"] is False
    assert stale["last_confirmed_at"] == "2026-08-31T03:42:00+00:00"


def test_concurrent_clicks_coalesce_one_provider_query(tmp_path) -> None:
    calls = 0
    gate = threading.Event()
    def provider(site, account):
        nonlocal calls
        calls += 1
        gate.wait(2)
        return success(site, account, 19)
    service = credits.CreditService(tmp_path, provider=provider)
    results = []
    threads = [threading.Thread(target=lambda: results.append(service.refresh("ultrapackv2", "account-a"))) for _ in range(5)]
    for thread in threads: thread.start()
    time.sleep(.05); gate.set()
    for thread in threads: thread.join(2)
    assert calls == 1 and len(results) == 5 and {item["credits"] for item in results} == {19}


def test_account_and_source_switch_never_leak_balance(tmp_path) -> None:
    amounts = {("ultrapackv2", "a"): 31, ("ultrapackv2", "b"): 17, ("plugintheme", "a"): 8}
    service = credits.CreditService(tmp_path, provider=lambda site, account: success(site, account, amounts[(site, account)]))
    for key in amounts: service.refresh(*key)
    assert service.cached("ultrapackv2", "a")["credits"] == 31
    assert service.cached("ultrapackv2", "b")["credits"] == 17
    assert service.cached("plugintheme", "a")["credits"] == 8


def test_public_logs_do_not_expose_session_or_secret(tmp_path) -> None:
    service = credits.CreditService(tmp_path, provider=lambda site, account: success(site, account, 5))
    serialized = str(service.refresh("ultrapackv2", "account-a")).lower()
    assert all(term not in serialized for term in ("cookie", "password", "consumer_secret", "session id", "token"))


def test_completed_download_requeries_provider_instead_of_local_decrement(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(credits, "_SERVICES", weakref.WeakSet())
    values, calls = iter((9, 7)), []
    def provider(site, account):
        amount = next(values); calls.append(amount); return success(site, account, amount)
    service = credits.CreditService(tmp_path, provider=provider)
    assert service.refresh("ultrapackv2", "account-a")["credits"] == 9
    credits.refresh_credits_after_download("ultrapackv2", "account-a")
    for _ in range(50):
        if len(calls) == 2: break
        time.sleep(.01)
    assert calls == [9, 7]
    assert service.cached("ultrapackv2", "account-a")["credits"] == 7
