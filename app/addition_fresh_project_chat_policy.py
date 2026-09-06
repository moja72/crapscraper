from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlsplit

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple


_INSTALLED = False
_PROJECT_TOKEN_RE = re.compile(r"/g/([^/?#]+)", re.I)
_NEW_CHAT_PATTERNS = (
    re.compile(r"^Novo$", re.I),
    re.compile(r"^New$", re.I),
    re.compile(r"^Novo chat$", re.I),
    re.compile(r"^New chat$", re.I),
    re.compile(r"^Criar chat$", re.I),
    re.compile(r"^Create chat$", re.I),
    re.compile(r"^Iniciar(?: novo)? chat$", re.I),
    re.compile(r"^Start(?: a)? new chat$", re.I),
)
_PROJECT_LOCAL_NEW_SELECTORS = (
    "button[aria-label*='novo chat' i]",
    "button[aria-label*='new chat' i]",
    "button[title*='novo chat' i]",
    "button[title*='new chat' i]",
    "[data-testid*='new-chat']",
    "[data-testid*='new_chat']",
)


def _project_token(value: str) -> str:
    raw = str(value or "").strip()
    match = _PROJECT_TOKEN_RE.search(raw)
    return str(match.group(1) if match else "").strip().casefold()


def _canonical_project_url(value: str) -> str:
    token = _project_token(value)
    if not token:
        return str(value or "").strip()
    return f"https://chatgpt.com/g/{token}/project"


def _project_route_candidates(value: str) -> list[str]:
    raw = str(value or "").strip()
    token = _project_token(raw)
    if not token:
        return [raw] if raw else []
    result = [
        f"https://chatgpt.com/g/{token}/project",
        f"https://chatgpt.com/g/{token}",
    ]
    return list(dict.fromkeys(item for item in result if item))


def _same_project(expected: str, actual: str) -> bool:
    left = _project_token(expected)
    right = _project_token(actual)
    if not left or left != right:
        return False
    try:
        host = str(urlsplit(str(actual or "")).hostname or "").lower()
    except Exception:
        return False
    return host in {"chatgpt.com", "www.chatgpt.com"}


def _conversation_turn_count(page: Any) -> int:
    """Return 0 only when the DOM positively shows no conversation turns.

    A layout with unclassified article nodes is treated as unknown (-1), never as
    empty. This keeps the isolation guard fail-closed when ChatGPT changes its DOM.
    """
    try:
        value = page.evaluate(
            """
            () => {
              const main = document.querySelector('main') || document;
              const turns = [...main.querySelectorAll('[data-testid*="conversation-turn"]')];
              if (turns.length) return turns.length;

              const roleNodes = [...main.querySelectorAll('[data-message-author-role]')];
              if (roleNodes.length) return roleNodes.length;

              // Some layouts keep turns as articles after removing role/test ids.
              // Their mere presence means we cannot prove the chat is empty.
              const articles = [...main.querySelectorAll('article')];
              if (articles.length) return -1;
              return 0;
            }
            """
        )
        return int(value)
    except Exception:
        return -1


def _composer_available(page: Any) -> bool:
    try:
        return one_click._composer(page) is not None
    except Exception:
        return False


def _blank_project_chat(page: Any, expected: str, before_url: str = "") -> bool:
    try:
        current = str(page.url or "").strip()
    except Exception:
        return False
    if not current or not _same_project(expected, current):
        return False

    # Reabrir exatamente uma conversa /c/ já usada não prova isolamento.
    if "/c/" in str(before_url or "") and current.rstrip("/") == str(before_url).rstrip("/"):
        return False

    turns = _conversation_turn_count(page)
    return turns == 0 and _composer_available(page)


def _wait_blank_project_chat(
    page: Any,
    expected: str,
    before_url: str = "",
    timeout_seconds: float = 12.0,
) -> bool:
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    while time.monotonic() < deadline:
        try:
            current = str(page.url or "").strip()
        except Exception:
            return False
        if current and not _same_project(expected, current):
            return False
        if _blank_project_chat(page, expected, before_url):
            return True
        try:
            page.wait_for_timeout(300)
        except Exception:
            time.sleep(0.3)
    return False


def _click_project_local_new(page: Any, expected: str) -> bool:
    try:
        before = str(page.url or "").strip()
    except Exception:
        before = ""

    scopes: list[Any] = []
    try:
        scopes.append(page.locator("main"))
    except Exception:
        pass
    scopes.append(page)

    for scope in scopes:
        for role in ("button", "link"):
            for pattern in _NEW_CHAT_PATTERNS:
                try:
                    nodes = scope.get_by_role(role, name=pattern)
                    count = min(int(nodes.count()), 12)
                except Exception:
                    continue
                for index in range(count):
                    try:
                        item = nodes.nth(index)
                        if not item.is_visible():
                            continue
                        try:
                            item.evaluate("el => el.click()")
                        except Exception:
                            item.click(force=True, timeout=5_000)
                        if _wait_blank_project_chat(page, expected, before, 10.0):
                            return True
                    except Exception:
                        continue

        for selector in _PROJECT_LOCAL_NEW_SELECTORS:
            try:
                nodes = scope.locator(selector)
                count = min(int(nodes.count()), 12)
            except Exception:
                continue
            for index in range(count):
                try:
                    item = nodes.nth(index)
                    if not item.is_visible():
                        continue
                    try:
                        item.evaluate("el => el.click()")
                    except Exception:
                        item.click(force=True, timeout=5_000)
                    if _wait_blank_project_chat(page, expected, before, 10.0):
                        return True
                except Exception:
                    continue

    return False


def _navigate_to_fresh_project_chat(page: Any, project_url: str) -> bool:
    for candidate in _project_route_candidates(project_url):
        navigated = False
        for wait_until in ("domcontentloaded", "commit"):
            try:
                page.goto(candidate, wait_until=wait_until, timeout=60_000)
                navigated = True
                break
            except Exception:
                continue
        if not navigated:
            continue

        try:
            page.wait_for_timeout(700)
        except Exception:
            time.sleep(0.7)

        if _wait_blank_project_chat(page, project_url, "", 6.0):
            return True
        if _click_project_local_new(page, project_url):
            return True
    return False


def _fresh_project_chat(context: Any, page: Any, job_id: str, url: str, label: str) -> Any:
    current = page if reconnect._page_is_alive(page) else reconnect._pick_page(context)
    expected = _canonical_project_url(url)
    last_error: BaseException | None = None

    for attempt in range(1, 4):
        try:
            one_click._emit(
                job_id,
                f"Abrindo {label} como um chat novo e vazio no projeto CS Automação…",
                step="chatgpt",
            )
            if _navigate_to_fresh_project_chat(current, expected):
                return current
            raise RuntimeError(
                "A rota do projeto abriu, mas não foi possível provar que a conversa está vazia."
            )
        except Exception as error:
            last_error = error
            if attempt < 3:
                current = reconnect._pick_page(context)
                time.sleep(0.8)

    raise RuntimeError(
        f"{label}: não foi possível criar e validar um chat NOVO e vazio dentro do projeto CS Automação. "
        "A execução foi interrompida para impedir reutilização de descrição ou imagem de outro produto."
    ) from last_error


def install_addition_fresh_project_chat_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    simple._fresh_project_chat = _fresh_project_chat
    _INSTALLED = True
