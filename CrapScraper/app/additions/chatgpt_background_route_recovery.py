from __future__ import annotations

import json
import re
import sys
import time
from typing import Any
from urllib.parse import urljoin

from app.additions import chatgpt_background_project_runtime as background
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery

_INSTALLED = False
_ORIGINAL_OPEN_PROJECT = background.open_project


def _absolute_chatgpt_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("/"):
        text = urljoin("https://chatgpt.com/", text)
    if text.startswith("https://chatgpt.com/") or text.startswith("https://www.chatgpt.com/"):
        return text
    return ""


def _project_landing_candidates(token: str) -> list[str]:
    """Return current and legacy project landing routes, preferring /project."""
    normalized = str(token or "").strip().casefold()
    if not normalized:
        return []
    return [
        f"https://chatgpt.com/g/{normalized}/project",
        f"https://chatgpt.com/g/{normalized}",
    ]


def _wait_signed_in(page: Any, timeout_ms: int = 15000) -> bool:
    """Wait for session evidence without treating a slow composer as logout."""
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000)
    while time.monotonic() < deadline:
        background._disable_closed_stage_overlay(page)
        compat._dismiss_common_dialogs(page)
        try:
            if compat._signed_in_evidence(page):
                return True
        except Exception:
            pass
        page.wait_for_timeout(350)

    try:
        if compat._looks_like_auth_wall(page):
            compat.ensure_authenticated(page)
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        pass
    return False


def _project_ready(page: Any, expected: str, timeout_ms: int = 18000) -> bool:
    """Require both a composer and the expected project token/route."""
    deadline = time.monotonic() + max(2.0, timeout_ms / 1000)
    while time.monotonic() < deadline:
        background._disable_closed_stage_overlay(page)
        compat._dismiss_common_dialogs(page)
        current = str(getattr(page, "url", "") or "").strip()
        if background._same_project_route(expected, current):
            if compat.composer(page, 1200) is not None:
                return True
        try:
            if compat._looks_like_auth_wall(page) and not compat._signed_in_evidence(page):
                compat.ensure_authenticated(page)
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass
        page.wait_for_timeout(400)
    return False


def _goto_project_candidate(page: Any, url: str, expected: str, timeout_ms: int = 18000) -> bool:
    target = _absolute_chatgpt_url(url)
    if not target:
        return False
    for wait_until in ("domcontentloaded", "commit"):
        try:
            page.goto(target, wait_until=wait_until, timeout=60000)
        except Exception:
            continue
        page.wait_for_timeout(900)
        if not _wait_signed_in(page, 9000):
            continue
        if _project_ready(page, expected, timeout_ms):
            return True
    return False


def _project_chat_hrefs(page: Any, token: str) -> list[str]:
    """Collect actual chats that belong to the saved project token."""
    if not token:
        return []
    selectors = (
        f'a[href*="/g/{token}/c/"]',
        f'a[href*="{token}"][href*="/c/"]',
    )
    found: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        try:
            nodes = page.locator(selector)
            count = min(nodes.count(), 40)
        except Exception:
            continue
        for index in range(count):
            try:
                href = _absolute_chatgpt_url(nodes.nth(index).get_attribute("href"))
            except Exception:
                href = ""
            if href and href not in seen and background._project_token(href) == token:
                seen.add(href)
                found.append(href)
    return found


def _try_project_new_button(page: Any, expected: str) -> bool:
    """Use a project-local new-chat control, never accepting a route outside the project."""
    patterns = (
        re.compile(r"^Novo$", re.I),
        re.compile(r"^New$", re.I),
        re.compile(r"^Novo chat$", re.I),
        re.compile(r"^New chat$", re.I),
        re.compile(r"^Criar chat$", re.I),
        re.compile(r"^Create chat$", re.I),
        re.compile(r"^Iniciar(?: novo)? chat$", re.I),
        re.compile(r"^Start(?: a)? new chat$", re.I),
    )
    for role in ("button", "link"):
        for pattern in patterns:
            try:
                scope = page.locator("main")
                item = scope.get_by_role(role, name=pattern).first
                if not item.count() or not item.is_visible():
                    continue
                try:
                    item.evaluate("el => el.click()")
                except Exception:
                    item.click(force=True, timeout=5000)
                page.wait_for_timeout(900)
                current = str(getattr(page, "url", "") or "").strip()
                if not background._same_project_route(expected, current):
                    continue
                if _project_ready(page, expected, 12000):
                    return True
            except legacy.ChatGPTPlaywrightError:
                raise
            except Exception:
                continue
    return False


def _recover_from_project_token(page: Any, saved: str) -> bool:
    """Recover from a stale/broken saved chat using the stable project token."""
    token = background._project_token(saved)
    if not token:
        return False
    expected = f"https://chatgpt.com/g/{token}"
    landing_candidates = _project_landing_candidates(token)

    # The canonical /project page is the stable fresh-chat landing route. Keep
    # /g/<token> only as a compatibility fallback for older UI revisions.
    for project_root in landing_candidates:
        try:
            page.goto(project_root, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            try:
                page.goto(project_root, wait_until="commit", timeout=60000)
            except Exception:
                continue
        page.wait_for_timeout(1000)
        if _wait_signed_in(page, 10000):
            if _project_ready(page, expected, 9000):
                return True
            for href in _project_chat_hrefs(page, token)[:8]:
                if _goto_project_candidate(page, href, expected, 12000):
                    return True
            if _try_project_new_button(page, expected):
                return True

    # If the project landing page is sparse, reload the home/sidebar and use the
    # hrefs React already rendered instead of clicking through the slideover UI.
    try:
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(900)
    except Exception:
        return False
    if not _wait_signed_in(page, 10000):
        return False
    try:
        compat._open_sidebar(page)
    except Exception:
        pass
    page.wait_for_timeout(700)
    background._disable_closed_stage_overlay(page)

    hrefs = _project_chat_hrefs(page, token)
    project_href = background._href_for_saved_project(page, saved)
    if project_href:
        hrefs.insert(0, project_href)
    seen: set[str] = set()
    for href in hrefs:
        if href in seen:
            continue
        seen.add(href)
        if _goto_project_candidate(page, href, expected, 14000):
            return True

    # Last token-safe attempt: revisit the canonical project landing route and
    # invoke only a local new-chat action. Never accept a global /c/ chat here.
    for project_root in landing_candidates:
        try:
            page.goto(project_root, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(900)
            if _wait_signed_in(page, 9000) and _try_project_new_button(page, expected):
                return True
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            continue
    return False


def open_project(page: Any) -> None:
    state = legacy._read_state()
    saved = project_recovery.saved_project_url(state)
    errors: list[str] = []

    if saved:
        try:
            if _goto_project_candidate(page, saved, saved, 16000):
                background._remember_project(page, saved)
                return
            errors.append("chat salvo sem compositor utilizável")
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception as error:
            errors.append(f"chat salvo: {error}")

        try:
            if _recover_from_project_token(page, saved):
                background._remember_project(page, saved)
                return
            errors.append("recuperação pelo token do projeto falhou")
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception as error:
            errors.append(f"token do projeto: {error}")

    try:
        _ORIGINAL_OPEN_PROJECT(page)
        current = str(getattr(page, "url", "") or "").strip()
        if saved and not background._same_project_route(saved, current):
            raise legacy.ChatGPTPlaywrightError(
                f"ChatGPT abriu fora do projeto {legacy.project_name()}."
            )
        background._remember_project(page, saved)
        return
    except legacy.ChatGPTPlaywrightError as error:
        errors.append(str(error))
    except Exception as error:
        errors.append(repr(error))

    diagnostic = compat._diagnostic(page, "background_project_route_recovery_failed")
    detail = " | ".join(errors[-4:])
    raise legacy.ChatGPTPlaywrightError(
        f"Projeto {legacy.project_name()} não pôde ser recuperado no navegador em segundo plano. "
        f"URL salva: {saved or '(ausente)'}. Diagnóstico salvo em {diagnostic}. "
        f"Tentativas: {detail}"
    )


def open_job_conversation(page: Any, job_id: str) -> None:
    """A stale per-job chat must fall back to the durable project recovery path."""
    item = legacy._job_state(str(job_id))
    conversation = str(item.get("conversation_url") or "").strip()
    project_saved = project_recovery.saved_project_url()

    if conversation:
        expected = project_saved or conversation
        try:
            if _goto_project_candidate(page, conversation, expected, 14000):
                return
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass

    open_project(page)
    current = str(getattr(page, "url", "") or "").strip()
    if current.startswith("https://chatgpt.com/"):
        legacy._update_job_state(
            str(job_id),
            conversation_url=current,
            cache_until=int(time.time()) + 30 * 24 * 60 * 60,
        )


def doctor() -> dict[str, Any]:
    with legacy._LOCK, background.browser(headless=True) as page:
        try:
            open_project(page)
            result = {
                "ok": True,
                "project": legacy.project_name(),
                "project_url": str(getattr(page, "url", "") or ""),
                "saved_project_url": project_recovery.saved_project_url(),
                "profile_dir": str(compat.profile_dir()),
                "composer_found": compat.composer(page, 2000) is not None,
                "browser_mode": background.browser_mode(True),
                "route_recovery": "project-token-canonical-landing",
            }
        except Exception as error:
            diagnostic = compat._diagnostic(page, "background_route_recovery_doctor_failed")
            result = {
                "ok": False,
                "error": str(error),
                "url": str(getattr(page, "url", "") or ""),
                "saved_project_url": project_recovery.saved_project_url(),
                "profile_dir": str(compat.profile_dir()),
                "browser_mode": background.browser_mode(True),
                "route_recovery": "project-token-canonical-landing",
                "diagnostic": diagnostic,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    compat.open_project = open_project
    legacy._open_project = open_project
    project_recovery.open_project = open_project
    background.open_project = open_project

    compat.open_job_conversation = open_job_conversation
    legacy._open_job_conversation = open_job_conversation
    _INSTALLED = True


def main() -> None:
    compat.install()
    project_recovery.install()
    background.install()
    install()
    command = (sys.argv[1] if len(sys.argv) > 1 else "doctor").strip().lower()
    if command in {"doctor", "diagnose", "diagnostico"}:
        doctor()
        return
    if command == "bootstrap":
        project_recovery.bootstrap()
        return
    if command == "status":
        payload = legacy.status()
        payload["saved_project_url"] = project_recovery.saved_project_url(payload)
        payload["browser_mode"] = background.browser_mode(True)
        payload["route_recovery"] = "project-token-canonical-landing"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    raise SystemExit("Use: python -m app.additions.chatgpt_background_route_recovery [doctor|bootstrap|status]")


__all__ = [
    "install",
    "open_project",
    "open_job_conversation",
    "doctor",
    "_project_chat_hrefs",
    "_project_landing_candidates",
    "_recover_from_project_token",
]


if __name__ == "__main__":
    main()
