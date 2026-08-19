from __future__ import annotations

import time
from typing import Any, Iterable, Mapping

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple


_INSTALLED = False


def _looks_like_user_prompt(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return bool(
        "escreva somente a breve descrição comercial deste produto" in normalized
        or (
            "regras obrigatórias" in normalized
            and "retorne somente a descrição final" in normalized
        )
    )


def _plausible_description(text: str) -> str:
    cleaned = simple._clean_description(text)
    if len(cleaned) < 180:
        return ""
    if _looks_like_user_prompt(cleaned):
        return ""
    lowered = cleaned.lower()
    if lowered.startswith("chatgpt plus") or "novo chat em [cs] automação" in lowered:
        return ""
    return cleaned


def _select_description_candidate(candidates: Iterable[Any]) -> str:
    selected = ""
    for item in candidates:
        if isinstance(item, Mapping):
            raw = str(item.get("text") or "")
        else:
            raw = str(item or "")
        candidate = _plausible_description(raw)
        if candidate:
            selected = candidate
    return selected


def _conversation_candidates(page: Any) -> list[dict[str, str]]:
    """Read visible conversation text without depending on one ChatGPT DOM attribute.

    The UI has changed more than once. Prefer explicit assistant nodes when they
    exist, then fall back to conversation turns and main-area articles. User
    turns are filtered here when their role is still available and again in
    Python by the known prompt wording.
    """
    try:
        result = page.evaluate(
            """
            () => {
              const out = [];
              const seen = new Set();
              const push = (node, source) => {
                if (!node) return;
                const text = String(node.innerText || node.textContent || '').trim();
                if (!text || seen.has(text)) return;
                seen.add(text);
                out.push({text, source});
              };

              document.querySelectorAll('[data-message-author-role="assistant"]').forEach(
                node => push(node, 'assistant-role')
              );

              document.querySelectorAll('main [data-testid^="conversation-turn-"]').forEach(turn => {
                const roleNode = turn.matches('[data-message-author-role]')
                  ? turn
                  : turn.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (role === 'user') return;
                const preferred =
                  turn.querySelector('[data-message-author-role="assistant"]') ||
                  turn.querySelector('.markdown') ||
                  turn.querySelector('[class*="markdown"]') ||
                  turn.querySelector('[class*="prose"]') ||
                  turn;
                push(preferred, 'conversation-turn');
              });

              document.querySelectorAll('main article').forEach(article => {
                const roleNode = article.matches('[data-message-author-role]')
                  ? article
                  : article.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (role === 'user') return;
                const preferred =
                  article.querySelector('[data-message-author-role="assistant"]') ||
                  article.querySelector('.markdown') ||
                  article.querySelector('[class*="markdown"]') ||
                  article.querySelector('[class*="prose"]') ||
                  article;
                push(preferred, 'article');
              });

              return out;
            }
            """
        )
    except Exception:
        return []

    rows: list[dict[str, str]] = []
    for item in result or []:
        if isinstance(item, Mapping):
            rows.append(
                {
                    "text": str(item.get("text") or ""),
                    "source": str(item.get("source") or ""),
                }
            )
    return rows


def _wait_plain_answer_fixed(
    context: Any,
    page: Any,
    before_count: int,
    job_id: str,
    url: str,
    *,
    timeout_seconds: int = 240,
) -> tuple[Any, str]:
    deadline = time.time() + timeout_seconds
    current = page
    last = ""
    stable = 0
    announced_fallback = False

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(
                context, current, job_id, url, timeout_seconds=60
            )

        candidate = ""
        direct_count = 0
        try:
            messages = one_click._assistant_messages(current)
            direct_count = messages.count()
            if direct_count > before_count:
                raw = str(messages.nth(direct_count - 1).inner_text() or "").strip()
                candidate = _plausible_description(raw)
        except Exception as error:
            if reconnect._is_retryable_browser_error(error):
                current = reconnect._pick_page(context)
                time.sleep(0.7)
                continue

        if not candidate:
            candidate = _select_description_candidate(_conversation_candidates(current))
            if candidate and not announced_fallback:
                one_click._emit(
                    job_id,
                    "Resposta encontrada pelo detector compatível com o layout atual do ChatGPT.",
                    step="chatgpt_description",
                    progress=26,
                )
                announced_fallback = True

        if candidate:
            if candidate == last:
                stable += 1
            else:
                last = candidate
                stable = 0

            if stable >= 2 and not simple._assistant_busy(current):
                return current, candidate

        time.sleep(0.9)

    if last:
        return current, last
    raise RuntimeError(
        "O ChatGPT respondeu na tela, mas o CrapScraper não conseguiu localizar o texto da descrição no DOM."
    )


def install_addition_chatgpt_response_reader_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    simple._wait_plain_answer = _wait_plain_answer_fixed
    _INSTALLED = True
