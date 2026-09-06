from __future__ import annotations

import time
from types import SimpleNamespace

from app.additions import chatgpt_job_cache_recovery_runtime as runtime


class FakePage:
    def __init__(self, result):
        self.result = result

    def evaluate(self, _script):
        return self.result


def test_safe_user_turn_count_accepts_proven_empty_conversation():
    assert runtime._safe_user_turn_count(FakePage({"ok": True, "users": 0})) == 0


def test_safe_user_turn_count_fails_closed_when_dom_is_unknown():
    assert runtime._safe_user_turn_count(FakePage({"ok": False, "users": -1})) == -1
    assert runtime._safe_user_turn_count(FakePage(None)) == -1


def test_safe_user_turn_count_preserves_existing_user_turns():
    assert runtime._safe_user_turn_count(FakePage({"ok": True, "users": 2})) == 2


def test_rehydrate_restores_exact_job_isolation(monkeypatch):
    calls = []
    written = {}
    now = int(time.time())
    job = {
        "job_id": "add-456",
        "comparison_item_id": "cmp-456",
        "product_name": "456 Industry - Repair Tools Shop",
        "kind": "theme",
        "source_url": "https://ultrapackv2.example/item/456",
        "source_version": "1.4.5",
        "chatgpt_conversation_url": "https://chatgpt.com/g/g-p-project/c/chat-456",
        "chatgpt_cache_until": now + 600,
    }

    monkeypatch.setattr(runtime, "_ORIGINAL_REHYDRATE", lambda _self, current: calls.append(current["job_id"]))
    monkeypatch.setattr(runtime, "_playwright_mode", lambda: True)
    monkeypatch.setattr(runtime.strict, "bind_job_identity", lambda current: calls.append(("bind", current["job_id"])) or "identity")
    monkeypatch.setattr(runtime.strict, "strict_job_conversation_fingerprint", lambda job_id: f"chat-fp:{job_id}")
    monkeypatch.setattr(runtime.legacy, "_update_job_state", lambda job_id, **values: written.update({"job_id": job_id, **values}) or values)

    runtime._rehydrate_chatgpt_cache(SimpleNamespace(), job)

    assert calls == ["add-456", ("bind", "add-456")]
    assert written["job_id"] == "add-456"
    assert written["conversation_url"].endswith("/c/chat-456")
    assert written["isolated_chat_version"] == runtime.strict._ISOLATION_VERSION
    assert written["isolated_chat_fingerprint"] == "chat-fp:add-456"
    assert written["cache_until"] == job["chatgpt_cache_until"]


def test_expired_cache_is_not_promoted_to_reusable(monkeypatch):
    calls = []
    job = {
        "job_id": "add-old",
        "chatgpt_conversation_url": "https://chatgpt.com/g/g-p-project/c/old",
        "chatgpt_cache_until": int(time.time()) - 1,
    }
    monkeypatch.setattr(runtime, "_ORIGINAL_REHYDRATE", lambda _self, current: calls.append("base"))
    monkeypatch.setattr(runtime, "_playwright_mode", lambda: True)
    monkeypatch.setattr(runtime.strict, "bind_job_identity", lambda _current: calls.append("bind"))
    monkeypatch.setattr(runtime.legacy, "_update_job_state", lambda *_args, **_kwargs: calls.append("write"))

    runtime._rehydrate_chatgpt_cache(SimpleNamespace(), job)

    assert calls == ["base"]
