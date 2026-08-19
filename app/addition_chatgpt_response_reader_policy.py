from __future__ import annotations

import time
from typing import Any, Iterable, Mapping

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple


_INSTALLED = False
_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
    "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress "
    "mais modernos e profissionais. Ele funciona com edição de arrastar e soltar, widgets premium, templates e "
    "construtores para tema, formulários e pop-ups, deixando a criação mais prática e reduzindo dependência de código no projeto."
)


def _description_prompt_refined(job: Mapping[str, Any]) -> str:
    kind = "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"
    kind_label = "tema WordPress" if kind == "theme" else "plugin WordPress"
    source_url = str(job.get("source_product_url") or "").strip()
    official_url = str(job.get("source_official_url") or "").strip()

    return f"""Gere apenas a breve descrição comercial deste produto para o e-commerce PluginTema.

PRODUTO
Nome: {job.get('source_name') or '-'}
Tipo: {kind_label}
Versão de referência: {job.get('source_version') or '-'}
Página da fonte: {source_url or '-'}
Página oficial: {official_url or '-'}

OBJETIVO DA DESCRIÇÃO
Escreva um único parágrafo em português do Brasil, com aproximadamente 400 a 500 caracteres e 2 ou 3 frases. O texto deve soar como uma descrição real de produto de e-commerce WordPress: claro, comercial, específico e natural.

ESTRUTURA DESEJADA
1. Comece com uma frase curta focada no principal benefício ou uso do produto.
2. Em seguida, mencione o nome do produto naturalmente e explique o que ele ajuda a criar, melhorar ou executar.
3. Finalize mostrando para que tipo de projeto ou usuário ele é útil, sem repetir ideias.

QUALIDADE
- Prefira informações concretas que possam ser inferidas com segurança pelo nome e pelas páginas fornecidas.
- Não invente recursos, integrações, compatibilidades ou números.
- Evite frases genéricas como "uma opção versátil", "solução completa", "presença online", "leve seu projeto para outro nível" e similares quando elas não acrescentarem informação.
- Não inclua a versão no texto final.
- Não use título, subtítulo, H1, H2, listas, HTML, Markdown, SEO, meta description, tags, categoria, observações ou explicações.
- Não escreva rótulos como "Descrição:" ou "Breve descrição:".

Use somente a estrutura, ritmo e extensão deste exemplo como referência; não copie o conteúdo:
"{_DESCRIPTION_EXAMPLE}"

Retorne SOMENTE o parágrafo final da breve descrição."""


def _looks_like_user_prompt(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    return bool(
        "escreva somente a breve descrição comercial deste produto" in normalized
        or "gere apenas a breve descrição comercial deste produto" in normalized
        or (
            "objetivo da descrição" in normalized
            and "retorne somente o parágrafo final" in normalized
        )
        or (
            "regras obrigatórias" in normalized
            and "retorne somente a descrição final" in normalized
        )
    )


def _plausible_description(text: str) -> str:
    cleaned = simple._clean_description(text)
    if len(cleaned) < 180 or len(cleaned) > 900:
        return ""
    if _looks_like_user_prompt(cleaned):
        return ""
    lowered = cleaned.lower()
    if lowered.startswith("chatgpt plus") or "novo chat em [cs] automação" in lowered:
        return ""
    if "projetos" in lowered and "chats" in lowered and "biblioteca" in lowered:
        return ""
    return cleaned


def _candidate_score(item: Any, text: str) -> float:
    source = ""
    if isinstance(item, Mapping):
        source = str(item.get("source") or "")
    source_weight = {
        "assistant-role": 400.0,
        "conversation-turn": 300.0,
        "article": 200.0,
        "markdown": 100.0,
    }.get(source, 0.0)
    length_bonus = max(0.0, 120.0 - abs(len(text) - 450) * 0.35)
    return source_weight + length_bonus


def _select_description_candidate(candidates: Iterable[Any]) -> str:
    selected = ""
    selected_score = -1.0
    for item in candidates:
        if isinstance(item, Mapping):
            raw = str(item.get("text") or "")
        else:
            raw = str(item or "")
        candidate = _plausible_description(raw)
        if not candidate:
            continue
        score = _candidate_score(item, candidate)
        if score >= selected_score:
            selected = candidate
            selected_score = score
    return selected


def _conversation_candidates(page: Any) -> list[dict[str, str]]:
    """Read visible answer text across current and recent ChatGPT DOM layouts."""
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

              document.querySelectorAll('main [data-testid^="conversation-turn-"], main [data-testid*="conversation-turn"]').forEach(turn => {
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

              document.querySelectorAll('main .markdown, main [class*="markdown"], main [class*="prose"]').forEach(
                node => push(node, 'markdown')
              );

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
    announced_wait = False
    started = time.time()

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(
                context, current, job_id, url, timeout_seconds=60
            )

        candidate = ""
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
                    "Resposta localizada no layout atual do ChatGPT; validando o texto…",
                    step="chatgpt_description",
                    progress=27,
                )
                announced_fallback = True

        if candidate:
            if candidate == last:
                stable += 1
            else:
                last = candidate
                stable = 0

            if stable >= 1 and not simple._assistant_busy(current):
                return current, candidate
        elif not announced_wait and (time.time() - started) >= 15:
            one_click._emit(
                job_id,
                "A resposta ainda não foi localizada no DOM; mantendo a leitura automática ativa…",
                step="chatgpt_description",
                progress=24,
            )
            announced_wait = True

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
    simple._description_prompt = _description_prompt_refined
    simple._wait_plain_answer = _wait_plain_answer_fixed
    _INSTALLED = True
