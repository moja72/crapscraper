from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery

_INSTALLED = False
_ORIGINAL_BROWSER = compat.browser
_ORIGINAL_OPEN_PROJECT = project_recovery.open_project


def browser_mode(requested_headless: bool | None = None) -> str:
    """Choose a browser mode that keeps ChatGPT project routes reliable.

    On Windows, ChatGPT project deep links have proved unreliable in Chromium
    headless even with a valid persistent session. The legacy flow worked in a
    normal browser, so the default runtime uses a real browser window minimized
    in the background. Set SCRAPER_CHATGPT_BROWSER_MODE=headless to force true
    headless operation, or visible to keep the window visible.
    """
    if requested_headless is False:
        return "visible"
    configured = (os.getenv("SCRAPER_CHATGPT_BROWSER_MODE") or "").strip().lower()
    if configured in {"headless", "background", "visible"}:
        return configured
    return "background" if sys.platform == "win32" else "headless"


def _minimize(page: Any) -> bool:
    try:
        session = page.context.new_cdp_session(page)
        info = session.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id is None:
            return False
        session.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "minimized"}},
        )
        return True
    except Exception:
        return False


@contextmanager
def browser(headless: bool | None = None):
    mode = browser_mode(headless)
    if mode == "headless":
        with _ORIGINAL_BROWSER(headless=True) as page:
            yield page
        return
    if mode == "visible":
        with _ORIGINAL_BROWSER(headless=False) as page:
            yield page
        return

    # Background mode deliberately uses the same headful browser behavior that
    # succeeds during bootstrap, but minimizes the window immediately. This is
    # materially different from Chromium headless for ChatGPT project routes.
    with _ORIGINAL_BROWSER(headless=False) as page:
        _minimize(page)
        yield page


def _project_token(value: str) -> str:
    try:
        path = urlparse(str(value or "")).path
    except Exception:
        return ""
    match = re.search(r"/g/(g-p-[^/]+)", path, re.I)
    return str(match.group(1) if match else "").casefold()


def _same_project_route(saved: str, current: str) -> bool:
    if not project_recovery.is_project_candidate_url(current):
        return False
    try:
        saved_path = urlparse(saved).path.rstrip("/")
        current_path = urlparse(current).path.rstrip("/")
    except Exception:
        return False
    if saved_path and saved_path == current_path:
        return True
    saved_token = _project_token(saved)
    current_token = _project_token(current)
    if saved_token:
        return saved_token == current_token
    if saved_path.startswith("/c/"):
        return current_path.startswith("/c/")
    return False


def _ready_on_saved_route(page: Any, saved: str, timeout_ms: int = 7000) -> bool:
    current = str(getattr(page, "url", "") or "").strip()
    if not _same_project_route(saved, current):
        return False
    compat._dismiss_common_dialogs(page)
    compat.ensure_authenticated(page)
    return compat.composer(page, timeout_ms) is not None or compat._try_new_chat(page)


def _navigate_saved(page: Any, saved: str) -> bool:
    # First try a lightweight commit navigation. ChatGPT may abort the original
    # navigation while its SPA takes over, so an ERR_ABORTED is not considered
    # fatal until we inspect the resulting page.
    try:
        page.goto(saved, wait_until="commit", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(2200)
    try:
        if _ready_on_saved_route(page, saved):
            return True
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        pass

    # If direct navigation was redirected to the home page, enter through the
    # authenticated origin first and assign the exact project/chat URL inside
    # the page. This avoids a second sidebar discovery dependency.
    try:
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        compat._dismiss_common_dialogs(page)
        compat.ensure_authenticated(page)
        page.evaluate("url => window.location.assign(url)", saved)
        page.wait_for_timeout(3000)
        if _ready_on_saved_route(page, saved):
            return True
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        pass
    return False


def open_project(page: Any) -> None:
    state = legacy._read_state()
    saved = str(state.get("project_url") or "").strip()
    if project_recovery.is_project_candidate_url(saved):
        if _navigate_saved(page, saved):
            legacy._update_state(
                project_url=str(getattr(page, "url", "") or saved),
                project_name=legacy.project_name(),
                profile_dir=str(compat.profile_dir()),
                background_route_ok=True,
                background_route_at=int(time.time()),
            )
            return

    try:
        _ORIGINAL_OPEN_PROJECT(page)
        return
    except Exception as error:
        diagnostic = compat._diagnostic(page, "background_project_navigation_failed")
        mode = browser_mode(True)
        raise legacy.ChatGPTPlaywrightError(
            f"Projeto {legacy.project_name()} não abriu no modo {mode}. "
            f"URL salva: {saved or '(ausente)'}. Diagnóstico salvo em {diagnostic}. "
            f"Erro anterior: {error}"
        ) from error


def doctor() -> dict[str, Any]:
    with legacy._LOCK, browser(headless=True) as page:
        try:
            open_project(page)
            result = {
                "ok": True,
                "project": legacy.project_name(),
                "project_url": str(getattr(page, "url", "") or ""),
                "profile_dir": str(compat.profile_dir()),
                "composer_found": compat.composer(page, 2000) is not None,
                "browser_mode": browser_mode(True),
            }
        except Exception as error:
            diagnostic = compat._diagnostic(page, "background_doctor_failed")
            result = {
                "ok": False,
                "error": str(error),
                "url": str(getattr(page, "url", "") or ""),
                "profile_dir": str(compat.profile_dir()),
                "browser_mode": browser_mode(True),
                "diagnostic": diagnostic,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    compat.browser = browser
    legacy._browser = browser
    compat.open_project = open_project
    legacy._open_project = open_project
    project_recovery.open_project = open_project
    compat.doctor = doctor
    project_recovery.doctor = doctor
    _INSTALLED = True


def main() -> None:
    compat.install()
    project_recovery.install()
    install()
    command = (sys.argv[1] if len(sys.argv) > 1 else "doctor").strip().lower()
    if command == "bootstrap":
        project_recovery.bootstrap()
        return
    if command in {"doctor", "diagnose", "diagnostico"}:
        doctor()
        return
    if command == "status":
        payload = legacy.status()
        payload["profile_dir"] = str(compat.profile_dir())
        payload["project_url_valid"] = project_recovery.is_project_candidate_url(str(payload.get("project_url") or ""))
        payload["browser_mode"] = browser_mode(True)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    raise SystemExit(
        "Use: python -m app.additions.chatgpt_background_project_runtime [bootstrap|doctor|status]"
    )


if __name__ == "__main__":
    main()
