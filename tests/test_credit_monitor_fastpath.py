from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import app.download_credit_fallback_policy as policy


def test_local_credit_is_explicitly_estimated():
    with patch.object(policy, "_used_today", return_value=7), patch.object(policy, "_daily_limit", return_value=40):
        payload = policy._fallback("ultrapackv2")

    assert payload["ok"] is True
    assert payload["remaining"] == 33
    assert payload["limit"] == 40
    assert payload["estimated"] is True
    assert payload["source"] == "crapscraper-local-ledger"


def test_confirmed_remote_credit_is_not_estimated():
    payload = policy._fallback(
        "plugintheme",
        {"ok": True, "remaining": 23, "limit": 50, "source": "remote-test"},
    )

    assert payload["remaining"] == 23
    assert payload["limit"] == 50
    assert payload["used"] == 27
    assert payload["estimated"] is False
    assert payload["source"] == "remote-test"


def test_fast_monitor_snapshot_is_local_and_reports_worker_state():
    with patch.object(policy, "_wordpress_manual_configured", return_value=False), \
         patch.object(policy, "_monitor_worker_alive", return_value=True), \
         patch("app.wordpress_manual_update.manual_monitor_snapshot", return_value={
             "monitor_status": "monitoring",
             "state": "Monitorando WordPress",
         }):
        payload = policy._fast_manual_monitor_snapshot(manager=None)

    assert payload["monitor_status"] == "monitoring"
    assert payload["state"] == "Monitorando WordPress"
    assert payload["worker_alive"] is True
    assert payload["fast_path"] is True


def test_accuracy_script_marks_estimates_and_refreshes_quickly():
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "download_credit_accuracy.js"
    ).read_text(encoding="utf-8")

    assert 'payload?.estimated ? "≈" : ""' in script
    assert 'fetch("/processos/creditos"' in script
    assert "10000" in script
