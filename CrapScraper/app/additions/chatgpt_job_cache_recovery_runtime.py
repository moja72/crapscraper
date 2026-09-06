from __future__ import annotations

import time
from typing import Any

from app.additions import chatgpt_playwright as legacy
from app.additions import strict_job_identity_runtime as strict
from app.additions.executor import AdditionExecutor, _CHAT_CACHE_SECONDS, _playwright_mode
from app.additions.images import ImageService


_INSTALLED = False
_ORIGINAL_REHYDRATE = None
_ORIGINAL_IMAGE_GENERATE = None


def _safe_user_turn_count(page: Any) -> int:
    """Return zero only when the conversation DOM is provably empty.

    Unknown conversation turns fail closed (-1). Generic project cards/articles are
    ignored because they are not conversation evidence.
    """
    try:
        result = page.evaluate(
            """
            () => {
              const main = document.querySelector('main');
              if (!main) return {ok: false, users: -1};

              const explicit = [...main.querySelectorAll('[data-message-author-role]')];
              if (explicit.length) {
                const unknown = explicit.some(node => {
                  const role = String(node.getAttribute('data-message-author-role') || '').toLowerCase();
                  return role !== 'user' && role !== 'assistant' && role !== 'system' && role !== 'tool';
                });
                if (unknown) return {ok: false, users: -1};
                return {
                  ok: true,
                  users: explicit.filter(node =>
                    String(node.getAttribute('data-message-author-role') || '').toLowerCase() === 'user'
                  ).length
                };
              }

              const turns = [...main.querySelectorAll('[data-testid^="conversation-turn-"]')];
              if (!turns.length) return {ok: true, users: 0};

              let users = 0;
              for (const turn of turns) {
                const roleNode = turn.matches('[data-message-author-role]')
                  ? turn : turn.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (!role) return {ok: false, users: -1};
                if (role === 'user') users += 1;
              }
              return {ok: true, users};
            }
            """
        )
    except Exception:
        return -1
    if not isinstance(result, dict) or not result.get("ok"):
        return -1
    try:
        return int(result.get("users", -1))
    except Exception:
        return -1


def _restore_exact_job_chat(job: dict[str, Any]) -> bool:
    """Restore only persisted evidence for the exact job, never bless a bare URL."""
    if not _playwright_mode():
        return False
    job_id = str(job.get("job_id") or "").strip()
    now = int(time.time())
    if not job_id:
        return False
    previous = legacy._job_state(job_id)
    identity = strict.job_identity_fingerprint(job)
    if previous.get("product_identity_fingerprint") not in (None, "", identity):
        strict.bind_job_identity(job)  # invalidates stale content/chat/image
        return False
    proof = job.get("chatgpt_provenance")
    if not isinstance(proof, dict):
        proof = {}
    # Older SQLite rows can still reuse existing full per-job JSON evidence.
    evidence = proof or previous
    url = str(evidence.get("conversation_url") or "").strip()
    from app.additions.chatgpt_project_url_recovery import is_project_candidate_url
    if (evidence.get("product_identity_fingerprint") != identity
            or int(evidence.get("isolated_chat_version") or 0) != strict._ISOLATION_VERSION
            or int(evidence.get("cache_until") or 0) <= now
            or not is_project_candidate_url(url) or "/c/" not in url
            or (job.get("chatgpt_conversation_url") and job["chatgpt_conversation_url"] != url)):
        return False
    strict.bind_job_identity(job)
    if evidence.get("isolated_chat_fingerprint") != strict.strict_job_conversation_fingerprint(job_id):
        return False
    legacy._update_job_state(job_id, **evidence)
    return True


def _rehydrate_chatgpt_cache(self: AdditionExecutor, job: dict[str, Any]) -> None:
    # Do not call the old URL-only hydrator before checking the evidence: that
    # would overwrite a valid conversation with an unproven SQLite URL.
    _restore_exact_job_chat(job)


def _image_generate(self: ImageService, job: dict[str, Any]):
    """Rebind exact provenance immediately before opening the image browser.

    Content generation and image generation intentionally use separate browser
    contexts. Repeating the deterministic job binding here closes the gap between
    them and lets Chat 2 continue from the exact product conversation saved after
    the description, without weakening image marker/hash validation.
    """
    _restore_exact_job_chat(job)
    return _ORIGINAL_IMAGE_GENERATE(self, job)


def install_chatgpt_job_cache_recovery_runtime() -> None:
    global _INSTALLED, _ORIGINAL_REHYDRATE, _ORIGINAL_IMAGE_GENERATE
    if _INSTALLED:
        return
    _ORIGINAL_REHYDRATE = AdditionExecutor._rehydrate_chatgpt_cache
    _ORIGINAL_IMAGE_GENERATE = ImageService.generate
    AdditionExecutor._rehydrate_chatgpt_cache = _rehydrate_chatgpt_cache
    ImageService.generate = _image_generate
    strict._user_turn_count = _safe_user_turn_count
    _INSTALLED = True


__all__ = [
    "install_chatgpt_job_cache_recovery_runtime",
    "_safe_user_turn_count",
    "_restore_exact_job_chat",
    "_rehydrate_chatgpt_cache",
    "_image_generate",
]
