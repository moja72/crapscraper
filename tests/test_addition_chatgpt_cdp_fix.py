from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.addition_chatgpt_cdp_fix as fix
import app.chatgpt_browser_assist as chatgpt


def test_project_url_is_used_when_old_generic_chatgpt_url_is_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "chatgpt.json"
    config_path.write_text(
        json.dumps({"conversation_url": "https://chatgpt.com/"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(chatgpt, "_CONFIG_PATH", config_path)
    monkeypatch.delenv("SCRAPER_CHATGPT_PROJECT_URL", raising=False)

    assert fix._conversation_url() == fix._PROJECT_URL
    assert fix._PROJECT_ID in fix._conversation_url()


def test_project_conversation_override_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = f"https://chatgpt.com/g/{fix._PROJECT_ID}/c/abc123"
    config_path = tmp_path / "chatgpt.json"
    config_path.write_text(
        json.dumps({"conversation_url": configured}),
        encoding="utf-8",
    )
    monkeypatch.setattr(chatgpt, "_CONFIG_PATH", config_path)
    monkeypatch.delenv("SCRAPER_CHATGPT_PROJECT_URL", raising=False)

    assert fix._conversation_url() == configured


def test_browser_args_use_remote_debugging_and_persistent_profile(tmp_path: Path) -> None:
    args = fix._browser_args(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        tmp_path / "profile",
        fix._PROJECT_URL,
        9333,
    )

    assert "--remote-debugging-port=9333" in args
    assert "--remote-debugging-address=127.0.0.1" in args
    assert any(value.startswith("--user-data-dir=") for value in args)
    assert fix._PROJECT_URL in args
