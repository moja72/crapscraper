from __future__ import annotations

import app.download_credit_fallback_policy as policy


def test_fallback_uses_local_daily_counter(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_USAGE_PATH", tmp_path / "credits.json")
    monkeypatch.setenv("SCRAPER_ULTRAPACKV2_DAILY_DOWNLOAD_LIMIT", "50")

    policy._record_download("ultrapackv2")
    policy._record_download("ultrapackv2")

    value = policy._fallback("ultrapackv2", {"ok": False})
    assert value["ok"] is True
    assert value["limit"] == 50
    assert value["used"] == 2
    assert value["remaining"] == 48
    assert value["estimated"] is True


def test_remote_credit_wins_over_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_USAGE_PATH", tmp_path / "credits.json")
    current = {"ok": True, "limit": 25, "remaining": 7, "used": 18, "source": "remote"}
    assert policy._fallback("plugintheme", current) == current


def test_default_daily_limits_match_sites(monkeypatch):
    monkeypatch.delenv("SCRAPER_ULTRAPACKV2_DAILY_DOWNLOAD_LIMIT", raising=False)
    monkeypatch.delenv("SCRAPER_PLUGINTHEME_DAILY_DOWNLOAD_LIMIT", raising=False)

    assert policy._daily_limit("ultrapackv2") == 40
    assert policy._daily_limit("plugintheme") == 50


def test_credit_snapshot_does_not_probe_remote_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_USAGE_PATH", tmp_path / "credits.json")
    monkeypatch.delenv("SCRAPER_DOWNLOAD_CREDITS_REMOTE_PROBE", raising=False)
    monkeypatch.delenv("SCRAPER_ULTRAPACKV2_DAILY_DOWNLOAD_LIMIT", raising=False)
    monkeypatch.delenv("SCRAPER_PLUGINTHEME_DAILY_DOWNLOAD_LIMIT", raising=False)

    def fail_if_called(_manager):
        raise AssertionError("remote credit probe must not run during normal panel polling")

    monkeypatch.setattr(policy, "_BASE_CREDIT_SNAPSHOT", fail_if_called)

    payload = policy._patched_credit_snapshot(None)

    assert payload["ok"] is True
    assert payload["ultrapackv2"]["remaining"] == 40
    assert payload["ultrapackv2"]["limit"] == 40
    assert payload["plugintheme"]["remaining"] == 50
    assert payload["plugintheme"]["limit"] == 50
