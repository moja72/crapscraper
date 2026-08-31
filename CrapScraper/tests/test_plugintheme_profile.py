from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app import plugintheme_profile
from app.collection.legacy_core.browser import AuthenticationState
from app.updates import source_auth


def test_profile_diagnostic_reads_persistent_cookie_store(tmp_path, monkeypatch) -> None:
    profile = tmp_path / "profile"
    database = profile / "Default" / "Network" / "Cookies"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE cookies(host_key TEXT, value TEXT, encrypted_value BLOB)")
        connection.executemany(
            "INSERT INTO cookies VALUES(?,?,?)",
            [
                (".plugintheme.net", "", b"encrypted"),
                ("api.plugintheme.net", "plain", b""),
                ("example.test", "other", b""),
            ],
        )
    (profile / "Default" / "Local Storage").mkdir(parents=True)
    monkeypatch.setattr(plugintheme_profile, "profile_path", lambda _account: profile)
    monkeypatch.setattr(plugintheme_profile, "configured", lambda _account: True)

    result = plugintheme_profile.profile_diagnostic("account-a")

    assert result["configured"] is True
    assert result["profile_exists"] is True
    assert result["cookie_count"] == 2
    assert result["browser_storage_exists"] is True
    assert result["persistence_mode"] == "persistent_browser_context"


def test_profile_diagnostic_counts_private_storage_state_cookies(tmp_path, monkeypatch) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "storage_state.json").write_text(
        '{"cookies":['
        '{"name":"session","value":"private","domain":".plugintheme.net","httpOnly":true},'
        '{"name":"other","value":"private","domain":"example.test","httpOnly":false}'
        '],"origins":[{"origin":"https://plugintheme.net","localStorage":[{"name":"auth","value":"private"}]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(plugintheme_profile, "profile_path", lambda _account: profile)
    monkeypatch.setattr(plugintheme_profile, "configured", lambda _account: True)

    result = plugintheme_profile.profile_diagnostic("account-a")

    assert result["storage_state_exists"] is True
    assert result["cookie_count"] == result["storage_state_cookie_count"] == 1
    assert result["httponly_cookie_count"] == 1
    assert result["storage_entry_count"] == 1


def test_storage_token_parser_accepts_json_and_never_needs_cookie_javascript() -> None:
    token = "a" * 50
    assert plugintheme_profile.find_access_token('{"auth":{"accessToken":"' + token + '"}}') == token
    assert plugintheme_profile.find_access_token("short") == ""


class FakePage:
    def __init__(self, url: str, storage: list[dict] | None = None):
        self.url = url
        self.storage = storage or []

    async def evaluate(self, _script):
        return self.storage


class FakeContext:
    def __init__(self, cookies: list[dict]):
        self._cookies = cookies
        self.saved_path = ""

    async def cookies(self):
        return self._cookies

    async def add_cookies(self, cookies):
        self._cookies.extend(cookies)

    async def storage_state(self, *, path):
        self.saved_path = path


class FakeBrowser:
    def __init__(self, url: str, cookies: list[dict], storage: list[dict] | None = None):
        self.page = FakePage(url, storage)
        self.browser_context = FakeContext(cookies)
        self.data = SimpleNamespace(user_agent="test-agent")

    async def goto(self, _url):
        return None


def _install_browser(monkeypatch, tmp_path: Path, browser, state: AuthenticationState) -> list[bool]:
    closed: list[bool] = []

    async def create(*_args, **_kwargs):
        return browser

    async def close(_browser):
        closed.append(True)

    async def determine(_page):
        return state

    monkeypatch.setattr("app.collection.legacy_core.browser.create_browser_session", create)
    monkeypatch.setattr("app.collection.legacy_core.browser.close_browser_session", close)
    monkeypatch.setattr("app.collection.legacy_core.browser.determine_authentication_state", determine)
    monkeypatch.setattr(source_auth, "profile_diagnostic", lambda account: {"profile_exists": True, "profile_path": f"profiles/{account}"})
    monkeypatch.setattr(source_auth, "storage_state_path", lambda account: tmp_path / account / "storage_state.json")
    monkeypatch.setattr(source_auth, "stored_state", lambda _account: {})
    monkeypatch.setattr(source_auth, "renewal_pending", lambda _account: False)
    monkeypatch.setattr(source_auth, "complete_manual_renewal", lambda _account: None)
    return closed


def test_functional_validation_loads_httponly_cookie_and_storage_token(tmp_path, monkeypatch) -> None:
    token = "b" * 50
    browser = FakeBrowser(
        "https://plugintheme.net/pt-BR/account",
        [{"name": "session", "value": "private", "domain": ".plugintheme.net", "path": "/", "httpOnly": True}],
        [{"scope": "localStorage", "key": "auth", "value": '{"token":"' + token + '"}'}],
    )
    closed = _install_browser(monkeypatch, tmp_path, browser, AuthenticationState.AUTHENTICATED)

    session, diagnostic = source_auth._run(source_auth._validated_plugintheme_session("account-a"))

    assert isinstance(session, requests.Session)
    assert session.headers["Authorization"] == f"Bearer {token}"
    assert diagnostic["authenticated"] is True
    assert diagnostic["cookie_count"] == 1 and diagnostic["httponly_cookie_count"] == 1
    assert diagnostic["storage_entry_count"] == 1 and diagnostic["storage_state_saved"] is True
    assert browser.browser_context.saved_path.endswith("storage_state.json") and closed == [True]


def test_functional_validation_restores_session_cookie_from_storage_state(tmp_path, monkeypatch) -> None:
    browser = FakeBrowser("https://plugintheme.net/pt-BR/account", [])
    closed = _install_browser(monkeypatch, tmp_path, browser, AuthenticationState.AUTHENTICATED)
    monkeypatch.setattr(
        source_auth,
        "stored_state",
        lambda _account: {"cookies": [
            {"name": "session", "value": "private", "domain": ".plugintheme.net", "path": "/", "httpOnly": True},
            {"name": "other", "value": "private", "domain": "example.test", "path": "/", "httpOnly": True},
        ]},
    )

    _session, diagnostic = source_auth._run(source_auth._validated_plugintheme_session("account-a"))

    assert diagnostic["storage_state_loaded"] is True
    assert diagnostic["cookie_count"] == diagnostic["httponly_cookie_count"] == 1
    assert closed == [True]


def test_manual_renewal_does_not_restore_stale_storage_cookie(tmp_path, monkeypatch) -> None:
    browser = FakeBrowser(
        "https://plugintheme.net/pt-BR/account",
        [{"name": "fresh", "value": "private", "domain": ".plugintheme.net", "path": "/", "httpOnly": True}],
    )
    _install_browser(monkeypatch, tmp_path, browser, AuthenticationState.AUTHENTICATED)
    monkeypatch.setattr(source_auth, "renewal_pending", lambda _account: True)
    monkeypatch.setattr(
        source_auth,
        "stored_state",
        lambda _account: {"cookies": [{"name": "stale", "value": "private", "domain": ".plugintheme.net", "path": "/"}]},
    )

    _session, diagnostic = source_auth._run(source_auth._validated_plugintheme_session("account-a"))

    assert diagnostic.get("storage_state_loaded") is not True
    assert [cookie["name"] for cookie in browser.browser_context._cookies] == ["fresh"]


def test_login_redirect_is_functionally_invalid_even_with_cookies(tmp_path, monkeypatch) -> None:
    browser = FakeBrowser(
        "https://plugintheme.net/pt-BR/auth/login",
        [{"name": "cloudflare", "value": "present", "domain": ".plugintheme.net", "path": "/", "httpOnly": True}],
    )
    closed = _install_browser(monkeypatch, tmp_path, browser, AuthenticationState.NOT_AUTHENTICATED)

    with pytest.raises(source_auth.PluginThemeAuthenticationError) as raised:
        source_auth._run(source_auth._validated_plugintheme_session("account-a"))

    assert raised.value.diagnostic["authenticated"] is False
    assert raised.value.diagnostic["login_redirect"] is True
    assert raised.value.diagnostic["cookie_count"] == 1 and closed == [True]
