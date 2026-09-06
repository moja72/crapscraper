from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from app.additions import chatgpt_background_project_runtime as background
from app.additions import chatgpt_background_route_recovery as route_recovery
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_project_url_recovery as project_recovery

_INSTALLED = False
_ISOLATION_VERSION = 1
_CACHE_SECONDS = 30 * 24 * 60 * 60


def job_conversation_fingerprint(job_id: str) -> str:
    raw = f"addition-chat-v{_ISOLATION_VERSION}|{str(job_id)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def conversation_reusable(item: dict[str, Any], job_id: str) -> bool:
    url = str(item.get("conversation_url") or "").strip()
    return bool(
        int(item.get("isolated_chat_version") or 0) == _ISOLATION_VERSION
        and str(item.get("isolated_chat_fingerprint") or "") == job_conversation_fingerprint(job_id)
        and project_recovery.is_project_candidate_url(url)
    )


def _save_isolated_chat(job_id: str, url: str) -> None:
    now = int(time.time())
    legacy._update_job_state(
        str(job_id),
        conversation_url=str(url),
        isolated_chat_version=_ISOLATION_VERSION,
        isolated_chat_fingerprint=job_conversation_fingerprint(job_id),
        isolated_chat_created_at=now,
        cache_until=now + _CACHE_SECONDS,
        # Any image produced before per-job isolation is untrusted on retry.
        image_ready=False,
        image_fingerprint="",
        image_sha256="",
        image_prompt_marker="",
    )


def _same_project(expected: str, current: str) -> bool:
    if not expected:
        return project_recovery.is_project_candidate_url(current)
    return background._same_project_route(expected, current)


def _open_existing_isolated(page: Any, job_id: str, item: dict[str, Any]) -> bool:
    if not conversation_reusable(item, job_id):
        return False
    url = str(item.get("conversation_url") or "").strip()
    expected = project_recovery.saved_project_url() or url
    try:
        return bool(route_recovery._goto_project_candidate(page, url, expected, 16000))
    except Exception:
        return False


def _click_project_new(page: Any, expected: str) -> bool:
    """Click only the project's exact `Novo`/`New` action, never global Novo chat."""
    patterns = (re.compile(r"^Novo$", re.I), re.compile(r"^New$", re.I))
    for role in ("button", "link"):
        for pattern in patterns:
            try:
                item = page.get_by_role(role, name=pattern).last
                if not item.count() or not item.is_visible():
                    continue
                try:
                    item.evaluate("el => el.click()")
                except Exception:
                    item.click(force=True, timeout=5000)
                page.wait_for_timeout(900)
                current = str(getattr(page, "url", "") or "").strip()
                if _same_project(expected, current) and compat.composer(page, 8000) is not None:
                    return True
            except Exception:
                continue
    return False


def _create_project_local_chat(page: Any, job_id: str) -> None:
    route_recovery.open_project(page)
    saved = project_recovery.saved_project_url() or str(getattr(page, "url", "") or "").strip()
    token = background._project_token(saved)
    expected = saved
    created = False

    # Best case: open the stable project landing route. If it stays on the root
    # and exposes a composer, sending the first prompt creates a brand-new chat
    # inside the project without touching any previous product conversation.
    if token:
        project_root = f"https://chatgpt.com/g/{token}"
        try:
            page.goto(project_root, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(900)
            route_recovery._wait_signed_in(page, 10000)
            current = str(getattr(page, "url", "") or "").rstrip("/")
            if current == project_root.rstrip("/") and compat.composer(page, 7000) is not None:
                expected = project_root
                created = True
            else:
                expected = project_root
                created = _click_project_new(page, project_root)
        except Exception:
            created = False

    # Fallback for UI variants where the project root redirects to the previous
    # chat: find the exact local `Novo` action. The legacy helper remains a final
    # fallback because it also validates the resulting g-p-* project route.
    if not created:
        try:
            route_recovery.open_project(page)
            expected = project_recovery.saved_project_url() or saved
            created = _click_project_new(page, expected)
        except Exception:
            created = False

    if not created:
        try:
            created = route_recovery._try_project_new_button(page, expected)
        except Exception:
            created = False

    current = str(getattr(page, "url", "") or "").strip()
    if not created or not _same_project(expected, current) or compat.composer(page, 7000) is None:
        diagnostic = compat._diagnostic(page, "isolated_job_chat_creation_failed")
        raise legacy.ChatGPTPlaywrightError(
            "Não foi possível criar um chat exclusivo deste produto dentro do projeto [CS] Automação. "
            "A execução foi interrompida para não reutilizar conteúdo ou imagem de outro produto. "
            f"Diagnóstico: {diagnostic}."
        )

    _save_isolated_chat(job_id, current)


def open_job_conversation(page: Any, job_id: str) -> None:
    item = legacy._job_state(str(job_id))
    if _open_existing_isolated(page, str(job_id), item):
        return
    _create_project_local_chat(page, str(job_id))


def candidate_belongs_to_current_prompt_turn(candidate: dict[str, Any], marker: str) -> bool:
    """Accept images only from the conversation turn answering this exact prompt.

    DOM position alone was insufficient because ChatGPT can render project/library
    images after the conversation in <main>. Both marker and image must resolve to
    real conversation turns, and no later user prompt may exist between them.
    """
    locator = candidate.get("locator")
    if locator is None:
        return False
    try:
        return bool(
            locator.evaluate(
                """
                (img, marker) => {
                  const main = img.closest('main') || document.querySelector('main');
                  if (!main) return false;
                  const textOf = node => String(node?.innerText || node?.textContent || '');
                  const roleOf = turn => {
                    if (!turn) return '';
                    const roleNode = turn.matches?.('[data-message-author-role]')
                      ? turn : turn.querySelector?.('[data-message-author-role]');
                    return String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                  };
                  const turnOf = node =>
                    node?.closest?.('[data-testid^="conversation-turn-"]') ||
                    node?.closest?.('article') || null;

                  const markerNodes = [
                    ...main.querySelectorAll('[data-message-author-role="user"]'),
                    ...main.querySelectorAll('[data-testid^="conversation-turn-"]'),
                    ...main.querySelectorAll('article')
                  ].filter(node => textOf(node).includes(marker));
                  const markerNode = markerNodes[markerNodes.length - 1];
                  const markerTurn = turnOf(markerNode);
                  const imageTurn = turnOf(img);
                  if (!markerTurn || !imageTurn || markerTurn === imageTurn) return false;
                  if (roleOf(imageTurn) === 'user') return false;

                  const conversationTurns = [...main.querySelectorAll('[data-testid^="conversation-turn-"]')];
                  const turns = conversationTurns.length
                    ? conversationTurns
                    : [...main.querySelectorAll('article')];
                  const markerIndex = turns.indexOf(markerTurn);
                  const imageIndex = turns.indexOf(imageTurn);
                  if (markerIndex < 0 || imageIndex <= markerIndex) return false;

                  for (let index = markerIndex + 1; index < imageIndex; index++) {
                    if (roleOf(turns[index]) === 'user') return false;
                  }
                  return true;
                }
                """,
                marker,
            )
        )
    except Exception:
        return False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions import chatgpt_playwright_image as image_runtime

    # Content generation resolves this dynamically from legacy; image generation
    # imported the function by name, so patch both references.
    legacy._open_job_conversation = open_job_conversation
    compat.open_job_conversation = open_job_conversation
    route_recovery.open_job_conversation = open_job_conversation
    image_runtime._open_job_conversation = open_job_conversation

    # Invalidate every pre-isolation image cache and require exact response-turn
    # provenance for all newly generated images.
    image_runtime._IMAGE_BINDING_VERSION = 3
    image_runtime._candidate_is_after_marker = candidate_belongs_to_current_prompt_turn
    _INSTALLED = True


__all__ = [
    "candidate_belongs_to_current_prompt_turn",
    "conversation_reusable",
    "install",
    "job_conversation_fingerprint",
    "open_job_conversation",
]
