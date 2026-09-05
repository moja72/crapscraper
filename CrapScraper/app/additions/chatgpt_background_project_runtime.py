from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urljoin, urlparse

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery

_INSTALLED = False
_ORIGINAL_BROWSER = compat.browser
_ORIGINAL_OPEN_PROJECT = project_recovery.open_project


def browser_mode(requested_headless: bool | None = None) -> str:
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
        session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "minimized"}})
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


def _disable_closed_stage_overlay(page: Any) -> None:
    """Neutralize a ChatGPT sidebar shell that can intercept pointer events while closed.

    The current web UI can keep #stage-slideover-sidebar over the project list even
    with data-state='closed'. In Playwright that makes a perfectly visible project
    locator unclickable. We only change pointer-events inside the automation browser.
    """
    try:
        page.evaluate(
            """
            () => {
              for (const el of document.querySelectorAll('#stage-slideover-sidebar[data-state="closed"], [data-state="closed"][id*="slideover-sidebar"]')) {
                el.style.pointerEvents = 'none';
              }
            }
            """
        )
    except Exception:
        pass


def _ready_on_saved_route(page: Any, saved: str, timeout_ms: int = 18000) -> bool:
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000)
    while time.monotonic() < deadline:
        current = str(getattr(page, "url", "") or "").strip()
        if _same_project_route(saved, current):
            _disable_closed_stage_overlay(page)
            compat._dismiss_common_dialogs(page)
            compat.ensure_authenticated(page)
            if compat.composer(page, 1200) is not None:
                return True
            if compat._try_new_chat(page):
                return True
        page.wait_for_timeout(450)
    return False


def _navigate_saved(page: Any, saved: str) -> bool:
    for wait_until in ("domcontentloaded", "commit"):
        try:
            page.goto(saved, wait_until=wait_until, timeout=60000)
        except Exception:
            pass
        page.wait_for_timeout(1400)
        try:
            if _ready_on_saved_route(page, saved):
                return True
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass

    try:
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(900)
        compat._dismiss_common_dialogs(page)
        compat.ensure_authenticated(page)
        page.evaluate("url => window.location.assign(url)", saved)
        page.wait_for_timeout(1600)
        if _ready_on_saved_route(page, saved):
            return True
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        pass
    return False


def _project_href(locator: Any, page: Any) -> str:
    try:
        href = locator.evaluate(
            """
            el => {
              const anchor = el.closest?.('a[href]');
              if (anchor?.href) return anchor.href;
              let node = el.parentElement;
              for (let i = 0; node && i < 6; i++, node = node.parentElement) {
                if (node.matches?.('a[href]') && node.href) return node.href;
                const child = node.querySelector?.('a[href]');
                if (child?.href) return child.href;
              }
              return '';
            }
            """
        )
    except Exception:
        href = ""
    text = str(href or "").strip()
    if text.startswith("/"):
        text = urljoin("https://chatgpt.com/", text)
    if text.startswith("https://chatgpt.com/") or text.startswith("https://www.chatgpt.com/"):
        return text
    return ""


def _open_project_from_sidebar(page: Any, saved: str = "") -> bool:
    """Open the project without relying on a pointer click.

    Prefer the anchor href from the visible project row. If the row is not an
    anchor, dispatch a DOM click, which is not blocked by an overlapping closed
    sidebar shell. This is intentionally a fallback after direct URL navigation.
    """
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1100)
    compat._dismiss_common_dialogs(page)
    compat.ensure_authenticated(page)
    compat._open_sidebar(page)
    page.wait_for_timeout(500)
    _disable_closed_stage_overlay(page)

    locator = compat._project_locator(page)
    if locator is None:
        return False

    href = _project_href(locator, page)
    if href:
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            page.goto(href, wait_until="commit", timeout=60000)
    else:
        try:
            locator.evaluate("el => el.click()")
        except Exception:
            try:
                locator.click(force=True, timeout=5000)
            except Exception:
                return False

    page.wait_for_timeout(1200)
    compat._dismiss_common_dialogs(page)
    compat.ensure_authenticated(page)

    current = str(getattr(page, "url", "") or "").strip()
    expected = saved or current
    if expected and _same_project_route(expected, current):
        if _ready_on_saved_route(page, expected):
            return True
    if compat.composer(page, 7000) is not None or compat._try_new_chat(page):
        current = str(getattr(page, "url", "") or "").strip()
        return project_recovery.is_project_candidate_url(current)
    return False


def _remember_project(page: Any, fallback: str = "") -> str:
    current = str(getattr(page, "url", "") or fallback).strip()
    durable = current if project_recovery.is_project_candidate_url(current) else fallback
    if durable and project_recovery.is_project_candidate_url(durable):
        legacy._update_state(
            project_url=durable,
            last_good_project_url=durable,
            project_name=legacy.project_name(),
            profile_dir=str(compat.profile_dir()),
            background_route_ok=True,
            background_route_at=int(time.time()),
        )
    return durable


def open_project(page: Any) -> None:
    state = legacy._read_state()
    saved = project_recovery.saved_project_url(state)
    errors: list[str] = []

    if saved:
        try:
            if _navigate_saved(page, saved):
                _remember_project(page, saved)
                return
        except Exception as error:
            errors.append(f"navegação direta: {error}")

    try:
        if _open_project_from_sidebar(page, saved):
            _remember_project(page, saved)
            return
    except Exception as error:
        errors.append(f"navegação pelo projeto: {error}")

    try:
        _ORIGINAL_OPEN_PROJECT(page)
        current = str(getattr(page, "url", "") or "").strip()
        if project_recovery.is_project_candidate_url(current):
            _remember_project(page, current)
        return
    except Exception as error:
        errors.append(f"fallback legado: {error}")
        diagnostic = compat._diagnostic(page, "background_project_navigation_failed")
        mode = browser_mode(True)
        detail = " | ".join(errors[-3:])
        raise legacy.ChatGPTPlaywrightError(
            f"Projeto {legacy.project_name()} não abriu no modo {mode}. "
            f"URL salva: {saved or '(ausente)'}. Diagnóstico salvo em {diagnostic}. "
            f"Tentativas: {detail}"
        ) from error


def doctor() -> dict[str, Any]:
    with legacy._LOCK, browser(headless=True) as page:
        try:
            open_project(page)
            result = {
                "ok": True,
                "project": legacy.project_name(),
                "project_url": str(getattr(page, "url", "") or ""),
                "saved_project_url": project_recovery.saved_project_url(),
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
                "saved_project_url": project_recovery.saved_project_url(),
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
        durable = project_recovery.saved_project_url(payload)
        if durable and not project_recovery.is_project_candidate_url(str(payload.get("project_url") or "")):
            payload["project_url"] = durable
            payload["project_url_recovered_from_backup"] = True
        payload["profile_dir"] = str(compat.profile_dir())
        payload["project_url_valid"] = bool(durable)
        payload["browser_mode"] = browser_mode(True)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    raise SystemExit("Use: python -m app.additions.chatgpt_background_project_runtime [bootstrap|doctor|status]")


if __name__ == "__main__":
    main()
