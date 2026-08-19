from __future__ import annotations

from pathlib import Path

import pytest

import app.addition_chatgpt_cdp_reconnect_policy as policy
import app.addition_chatgpt_cdp_fix as cdp


class _Page:
    def __init__(self, url: str) -> None:
        self.url = url

    def is_closed(self) -> bool:
        return False


class _Context:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages
        self.new_page_calls = 0

    def new_page(self) -> _Page:
        self.new_page_calls += 1
        page = _Page("about:blank")
        self.pages.append(page)
        return page


def test_target_closed_error_is_retryable() -> None:
    error = RuntimeError("Page.wait_for_timeout: Target page, context or browser has been closed")
    assert policy._is_retryable_browser_error(error) is True


def test_login_urls_are_not_treated_as_project_pages() -> None:
    assert policy._is_login_url("https://auth.openai.com/log-in") is True
    assert policy._is_login_url("https://chatgpt.com/auth/login") is True
    assert policy._is_login_url(cdp._PROJECT_URL) is False


def test_existing_project_tab_is_reused_instead_of_creating_second_page() -> None:
    regular = _Page("https://chatgpt.com/")
    project = _Page(cdp._PROJECT_URL)
    context = _Context([regular, project])

    selected = policy._pick_page(context)

    assert selected is project
    assert context.new_page_calls == 0


def test_stable_browser_args_keep_project_url_last(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def base(browser: str, profile_dir: Path, url: str, port: int) -> list[str]:
        return [
            browser,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            url,
        ]

    monkeypatch.setattr(policy, "_ORIGINAL_BROWSER_ARGS", base)
    result = policy._stable_browser_args("chrome.exe", tmp_path / "profile", cdp._PROJECT_URL, 9333)

    assert result[-1] == cdp._PROJECT_URL
    assert "--new-window" in result
    assert "--disable-background-mode" in result
    assert "--disable-session-crashed-bubble" in result
    assert "--disable-features=AutoDeElevate" in result
