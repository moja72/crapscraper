from __future__ import annotations

import time
from typing import Any

from app.additions import chatgpt_playwright as legacy
from app.additions import strict_job_identity_runtime as strict
from app.additions.executor import AdditionExecutor, _CHAT_CACHE_SECONDS, _playwright_mode


_INSTALLED = False
_ORIGINAL_REHYDRATE = None


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


def _rehydrate_chatgpt_cache(self: AdditionExecutor, job: dict[str, Any]) -> None:
    """Restore both URL and provenance for the exact persisted addition job.

    The SQLite row is keyed by this job and stores the concrete ChatGPT URL after
    content generation. On a restart/retry we may safely reconstruct the isolation
    fingerprint from the same immutable job identity instead of discarding the
    conversation and trying to create an unrelated second chat for the image.
    """
    _ORIGINAL_REHYDRATE(self, job)
    if not _playwright_mode():
        return

    job_id = str(job.get("job_id") or "").strip()
    url = str(job.get("chatgpt_conversation_url") or "").strip()
    cache_until = int(job.get("chatgpt_cache_until") or 0)
    now = int(time.time())
    if not job_id or not url.startswith("https://chatgpt.com/"):
        return
    if cache_until and cache_until < now:
        return

    # bind_job_identity invalidates stale state if a job id ever points at another
    # product/source. Only after that proof do we restore the URL for this job.
    strict.bind_job_identity(job)
    legacy._update_job_state(
        job_id,
        conversation_url=url,
        isolated_chat_version=strict._ISOLATION_VERSION,
        isolated_chat_fingerprint=strict.strict_job_conversation_fingerprint(job_id),
        isolated_chat_created_at=now,
        cache_until=cache_until if cache_until > now else now + _CHAT_CACHE_SECONDS,
    )


def install_chatgpt_job_cache_recovery_runtime() -> None:
    global _INSTALLED, _ORIGINAL_REHYDRATE
    if _INSTALLED:
        return
    _ORIGINAL_REHYDRATE = AdditionExecutor._rehydrate_chatgpt_cache
    AdditionExecutor._rehydrate_chatgpt_cache = _rehydrate_chatgpt_cache
    strict._user_turn_count = _safe_user_turn_count
    _INSTALLED = True


__all__ = [
    "install_chatgpt_job_cache_recovery_runtime",
    "_safe_user_turn_count",
    "_rehydrate_chatgpt_cache",
]
