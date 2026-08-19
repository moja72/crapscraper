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
