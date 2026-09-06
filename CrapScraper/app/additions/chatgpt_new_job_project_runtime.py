from __future__ import annotations

import re
import time
from typing import Any

from app.additions import chatgpt_background_project_runtime as background
from app.additions import chatgpt_background_route_recovery as route_recovery
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_playwright_image as image_runtime
from app.additions import chatgpt_product_isolation_runtime as isolation
from app.additions import chatgpt_project_url_recovery as project_recovery
from app.additions import product_content_contract_runtime as product_contract
from app.additions import strict_job_identity_runtime as strict

_INSTALLED = False
_CONTENT_CONTRACT_VERSION = 4


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


def _saved_project_url(page: Any) -> str:
    """Return the durable project URL without trying to open an old conversation."""
    try:
        saved = str(project_recovery.saved_project_url() or "").strip()
    except Exception:
        saved = ""
    if saved:
        return saved

    try:
        state = legacy._read_state()
    except Exception:
        state = {}
    for key in ("last_good_project_url", "project_url"):
        value = str(state.get(key) or "").strip() if isinstance(state, dict) else ""
        if value:
            return value

    current = str(getattr(page, "url", "") or "").strip()
    return current if project_recovery.is_project_candidate_url(current) else ""


def _project_landing_url(token: str) -> str:
    """Return the canonical ChatGPT project page used to start a fresh chat."""
    normalized = str(token or "").strip().casefold()
    return f"https://chatgpt.com/g/{normalized}/project" if normalized else ""


def _project_route_candidates(project_url: str) -> list[str]:
    """Prefer the canonical /project page, retaining the old root as compatibility fallback."""
    token = background._project_token(project_url)
    if not token:
        return [project_url] if project_url else []

    candidates = [
        _project_landing_url(token),
        f"https://chatgpt.com/g/{token}",
    ]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _wait_for_blank_project_chat(
    page: Any,
    expected: str,
    before_url: str = "",
    timeout_ms: int = 12000,
) -> bool:
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000)
    concrete_before = "/c/" in str(before_url or "")

    while time.monotonic() < deadline:
        try:
            background._disable_closed_stage_overlay(page)
        except Exception:
            pass
        try:
            compat._dismiss_common_dialogs(page)
        except Exception:
            pass

        current = str(getattr(page, "url", "") or "").strip()
        if current and not background._same_project_route(expected, current):
            return False

        try:
            blank = strict._is_blank_project_chat(page, expected)
        except Exception:
            blank = False

        if blank:
            if concrete_before and current.rstrip("/") == str(before_url).rstrip("/"):
                page.wait_for_timeout(250)
                continue
            return True

        page.wait_for_timeout(300)

    return False


def _click_project_local_new(page: Any, expected: str) -> bool:
    """Create a fresh project-local chat across current ChatGPT button labels.

    The current project landing page uses a dedicated ``/project`` route and may
    expose the action as ``Novo chat``/``New chat`` rather than only ``Novo``.
    Every click is accepted only if the resulting route remains in the same
    project and the conversation is provably empty.
    """
    before = str(getattr(page, "url", "") or "").strip()

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
                    count = min(nodes.count(), 12)
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
                            item.click(force=True, timeout=5000)
                        page.wait_for_timeout(500)
                        if _wait_for_blank_project_chat(page, expected, before, 10000):
                            return True
                    except Exception:
                        continue

        for selector in _PROJECT_LOCAL_NEW_SELECTORS:
            try:
                nodes = scope.locator(selector)
                count = min(nodes.count(), 12)
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
                        item.click(force=True, timeout=5000)
                    page.wait_for_timeout(500)
                    if _wait_for_blank_project_chat(page, expected, before, 10000):
                        return True
                except Exception:
                    continue

    return False


def _direct_blank_project(page: Any, project_root: str) -> bool:
    """Open the stable project landing page first and prove a blank local chat exists."""
    for candidate in _project_route_candidates(project_root):
        navigated = False
        for wait_until in ("domcontentloaded", "commit"):
            try:
                page.goto(candidate, wait_until=wait_until, timeout=60000)
                navigated = True
                break
            except Exception:
                continue
        if not navigated:
            continue

        page.wait_for_timeout(900)
        try:
            if not route_recovery._wait_signed_in(page, 10000):
                continue
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            continue

        if _wait_for_blank_project_chat(page, project_root, "", 7000):
            return True

        if _click_project_local_new(page, project_root):
            return True

        try:
            route_recovery._try_project_new_button(page, project_root)
            page.wait_for_timeout(500)
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            continue

        if _wait_for_blank_project_chat(page, project_root, "", 9000):
            return True

    return False


def _recover_blank_project(page: Any, saved: str, project_root: str) -> bool:
    """Recover through the project token, never through the stale physical-click path."""
    try:
        recovered = route_recovery._recover_from_project_token(page, saved)
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        recovered = False

    if recovered:
        if _wait_for_blank_project_chat(page, project_root, "", 5000):
            return True
        if _click_project_local_new(page, project_root):
            return True
        try:
            if strict.strict_click_project_new(page, project_root):
                return True
        except Exception:
            pass

    # A stale recovery implementation may still use /g/<token> without /project.
    # Retry the canonical landing route directly before giving up.
    return _direct_blank_project(page, project_root)


def create_project_local_chat(page: Any, job_id: str) -> None:
    """Create a new, empty project chat without first reopening the old saved chat.

    The project token (g-p-*) is the durable identity. A fresh addition opens the
    canonical ``/g/<token>/project`` landing route and only accepts a conversation
    that stays inside that project and has zero user turns.
    """
    saved = _saved_project_url(page)
    token = background._project_token(saved)
    errors: list[str] = []

    if not token:
        try:
            route_recovery.open_project(page)
        except Exception as error:
            errors.append(f"descoberta do projeto: {error}")
        saved = _saved_project_url(page)
        token = background._project_token(saved)

    if not token:
        diagnostic = compat._diagnostic(page, "new_job_project_token_missing")
        raise legacy.ChatGPTPlaywrightError(
            "Projeto [CS] Automação sem identificador g-p-* persistido. "
            "Execute o bootstrap uma vez e abra o projeto. "
            f"Diagnóstico: {diagnostic}."
        )

    project_root = _project_landing_url(token)
    created = False

    try:
        created = _direct_blank_project(page, project_root)
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception as error:
        errors.append(f"rota direta do projeto: {error}")

    if not created:
        try:
            created = _recover_blank_project(page, saved, project_root)
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception as error:
            errors.append(f"recuperação pelo token: {error}")

    if not created:
        diagnostic = compat._diagnostic(page, "new_job_blank_project_chat_failed")
        detail = " | ".join(errors[-3:])
        suffix = f" Tentativas: {detail}." if detail else ""
        raise legacy.ChatGPTPlaywrightError(
            "Não foi possível criar um chat NOVO e vazio para este produto no projeto [CS] Automação. "
            "A execução foi interrompida para impedir reutilização de conteúdo de outro produto. "
            f"Diagnóstico: {diagnostic}.{suffix}"
        )

    now = int(time.time())
    legacy._update_job_state(
        str(job_id),
        conversation_url=str(getattr(page, "url", "") or project_root).strip(),
        isolated_chat_version=strict._ISOLATION_VERSION,
        isolated_chat_fingerprint=strict.strict_job_conversation_fingerprint(str(job_id)),
        isolated_chat_created_at=now,
        cache_until=now + 30 * 24 * 60 * 60,
        content_ready=False,
        content_fingerprint="",
        image_ready=False,
        image_fingerprint="",
        image_sha256="",
        image_prompt_marker="",
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    strict.strict_create_project_local_chat = create_project_local_chat
    isolation._create_project_local_chat = create_project_local_chat

    legacy._open_job_conversation = strict.strict_open_job_conversation
    compat.open_job_conversation = strict.strict_open_job_conversation
    route_recovery.open_job_conversation = strict.strict_open_job_conversation
    image_runtime._open_job_conversation = strict.strict_open_job_conversation

    strict._CONTENT_CONTRACT_VERSION = _CONTENT_CONTRACT_VERSION
    product_contract._CONTENT_CONTRACT_VERSION = _CONTENT_CONTRACT_VERSION

    _INSTALLED = True


__all__ = [
    "create_project_local_chat",
    "install",
    "_click_project_local_new",
    "_direct_blank_project",
    "_project_landing_url",
    "_project_route_candidates",
    "_recover_blank_project",
    "_saved_project_url",
    "_wait_for_blank_project_chat",
]
