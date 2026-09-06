from __future__ import annotations

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


def _direct_blank_project(page: Any, project_root: str) -> bool:
    """Open the stable project root first and prove that a blank local chat exists.

    A new addition must not depend on reopening the previously saved /c/ URL. The
    old route can be stale or temporarily fail while the project itself remains
    perfectly usable. This is the failure mode that blocked new products at the
    generating_description stage.
    """
    try:
        page.goto(project_root, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        try:
            page.goto(project_root, wait_until="commit", timeout=60000)
        except Exception:
            return False

    page.wait_for_timeout(900)
    try:
        if not route_recovery._wait_signed_in(page, 10000):
            return False
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        return False

    if strict._is_blank_project_chat(page, project_root):
        return True

    # First use the stricter helper: it accepts success only when the resulting
    # route belongs to this project and contains zero user turns.
    try:
        if strict.strict_click_project_new(page, project_root):
            return True
    except Exception:
        pass

    # The current ChatGPT project page often exposes a local "Novo" control in
    # <main>. Use that as a second route, but still verify that the result is blank.
    before = str(getattr(page, "url", "") or "").strip()
    try:
        route_recovery._try_project_new_button(page, project_root)
        page.wait_for_timeout(700)
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        return False

    current = str(getattr(page, "url", "") or "").strip()
    if "/c/" in before and current.rstrip("/") == before.rstrip("/"):
        return False
    return strict._is_blank_project_chat(page, project_root)


def _recover_blank_project(page: Any, saved: str, project_root: str) -> bool:
    """Recover through the project token, never through the stale physical-click path."""
    try:
        if not route_recovery._recover_from_project_token(page, saved):
            return False
    except legacy.ChatGPTPlaywrightError:
        raise
    except Exception:
        return False

    if strict._is_blank_project_chat(page, project_root):
        return True
    try:
        return bool(strict.strict_click_project_new(page, project_root))
    except Exception:
        return False


def create_project_local_chat(page: Any, job_id: str) -> None:
    """Create a new, empty project chat without first reopening the old saved chat.

    Previously ``strict_create_project_local_chat`` started by calling
    ``route_recovery.open_project``. If the saved concrete conversation failed to
    reopen, the function aborted before reaching its own stable project-root
    fallback. A completely new product therefore failed before its first prompt.

    The project token (g-p-*) is the durable identity. When it is known, this
    runtime goes directly to ``/g/<token>`` and creates a blank project-local chat.
    The old conversation is only used as a source of that token, never as a gate.
    """
    saved = _saved_project_url(page)
    token = background._project_token(saved)
    errors: list[str] = []

    # Profiles created before project-token persistence may not have a token yet.
    # In that one case, allow route recovery to discover it, then immediately
    # switch back to the stable project-root flow.
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

    project_root = f"https://chatgpt.com/g/{token}"
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

    # Replace only the new-chat creation primitive. strict_open_job_conversation
    # resolves this name from its module globals at call time, so all content and
    # image flows immediately gain the safer route.
    strict.strict_create_project_local_chat = create_project_local_chat
    isolation._create_project_local_chat = create_project_local_chat

    # Reassert the strict job opener after every prior compatibility layer.
    legacy._open_job_conversation = strict.strict_open_job_conversation
    compat.open_job_conversation = strict.strict_open_job_conversation
    route_recovery.open_job_conversation = strict.strict_open_job_conversation
    image_runtime._open_job_conversation = strict.strict_open_job_conversation

    # strict_job_identity_runtime used to downgrade the content cache contract to
    # v3 during application bootstrap. Keep v4 so old/list-style descriptions are
    # not silently reused after the catalog contract update.
    strict._CONTENT_CONTRACT_VERSION = _CONTENT_CONTRACT_VERSION
    product_contract._CONTENT_CONTRACT_VERSION = _CONTENT_CONTRACT_VERSION

    _INSTALLED = True


__all__ = [
    "create_project_local_chat",
    "install",
    "_direct_blank_project",
    "_recover_blank_project",
    "_saved_project_url",
]
