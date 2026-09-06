from __future__ import annotations

import json
import re
import time
from typing import Any, Mapping

from app.additions import chatgpt_playwright as legacy
from app.additions.content import normalize_list, valid_content
from app.additions.source import clean_developer, clean_official_url

_BEGIN = "<<<CRAPSCRAPER_JSON_BEGIN>>>"
_END = "<<<CRAPSCRAPER_JSON_END>>>"
_INSTALLED = False


def _rendered_text(value: Any) -> str:
    """Normaliza a representação visual do Markdown do ChatGPT.

    A UI atual pode expor `product\\_name` e `<<\\<CRAPSCRAPER...` mesmo
    quando o modelo gerou underscores/ângulos normais. Essa normalização serve
    apenas para leitura do DOM, não altera conteúdo antes de enviar.
    """
    from app.additions.chatgpt_json_recovery_runtime import _rendered
    return _rendered(value)


def _body_text(page: Any) -> str:
    try:
        return _rendered_text(page.locator("body").inner_text(timeout=3000) or "")
    except Exception:
        return ""


def _submit(page: Any, prompt: str) -> None:
    composer = legacy._composer(page, 7000)
    if composer is None:
        legacy._ensure_authenticated(page)
        composer = legacy._composer(page, 3000)
    if composer is None:
        raise legacy.ChatGPTPlaywrightError("Campo de mensagem do ChatGPT não encontrado.")
    composer.click()
    composer.fill(prompt)
    try:
        composer.press("Enter")
    except Exception:
        send = page.locator(
            "button[data-testid='send-button'], button[aria-label*='Enviar' i], button[aria-label*='Send' i]"
        ).first
        if not send.count():
            raise
        send.click()


def _assistant_busy(page: Any) -> bool:
    if legacy._stop_visible(page):
        return True
    for selector in (
        "button[data-testid='stop-button']",
        "button[aria-label*='Interromper' i]",
        "button[aria-label*='Stop generating' i]",
    ):
        try:
            node = page.locator(selector).first
            if node.count() and node.is_visible():
                return True
        except Exception:
            continue
    return False


def _extract_last_marked(text: str) -> str:
    raw = _rendered_text(text)
    end = raw.rfind(_END)
    if end < 0:
        return ""
    begin = raw.rfind(_BEGIN, 0, end)
    if begin < 0:
        return ""
    return raw[begin + len(_BEGIN) : end].strip().strip("`").strip()


def _conversation_candidates(page: Any, marker: str = "") -> list[str]:
    """Read only assistant responses following the exact request turn.

    Role, conversation-turn and article layouts are supported. Unproven DOM is
    diagnostic evidence, never a fallback source of product content.
    """
    try:
        rows = page.evaluate(
            """
            marker => {
              const textOf = n => String(n?.innerText || n?.textContent || '').trim();
              const selector = '[data-message-author-role], [data-testid^="conversation-turn-"], article';
              const nodes = [...document.querySelectorAll('main ' + selector.split(', ').join(', main '))];
              const turns = nodes.filter(n => !nodes.some(parent => parent !== n && parent.contains(n)));
              const roleOf = n => {
                const explicit = n.matches('[data-message-author-role]') ? n : n.querySelector('[data-message-author-role]');
                if (explicit) return explicit.getAttribute('data-message-author-role');
                const label = String(n.getAttribute('aria-label') || '').toLowerCase();
                if (/you said|você disse/.test(label)) return 'user';
                if (/chatgpt said|chatgpt disse/.test(label)) return 'assistant';
                return '';
              };
              let anchor = -1;
              if (marker) {
                anchor = turns.findLastIndex(n => roleOf(n) === 'user' && textOf(n).includes(marker));
                if (anchor < 0) return [];
              }
              const out = [];
              for (let i = anchor + 1; i < turns.length; i++) {
                const role = roleOf(turns[i]);
                if (marker && (!role || role === 'user')) break;
                if (role !== 'assistant') continue;
                // Raw textContent can preserve valid JSON lost by innerText.
                const code = turns[i].querySelector('pre code');
                if (code?.textContent) out.push({text: code.textContent, source: 'code'});
                out.push({text: textOf(turns[i]), source: 'assistant-turn'});
              }
              return out;
            }
            """, marker,
        )
    except Exception:
        return []
    return [_rendered_text(row.get("text") if isinstance(row, Mapping) else row).strip()
            for row in rows or [] if row]


def _repair_json_candidate(candidate: str) -> str:
    text = str(candidate or "").strip().strip("`").strip()
    text = re.sub(r"\\([_<>])", r"\1", text)
    return text


def _extract_json(text: str, expected_product: str = "") -> dict[str, Any] | None:
    from app.additions.chatgpt_json_recovery_runtime import extract_json
    return extract_json(text, expected_product)


def _looks_like_content_json(text: str, expected_product: str = "") -> bool:
    from app.additions.chatgpt_json_recovery_runtime import content_object
    payload = _extract_json(text, expected_product)
    return isinstance(payload, dict) and content_object(payload)


def _wait_content_response(page: Any, prompt: str, timeout_seconds: int | None = None,
                           job: dict[str, Any] | None = None) -> str:
    from uuid import uuid4
    from app.additions.chatgpt_json_recovery_runtime import response_kind
    expected = str((job or {}).get("product_name") or "")
    marker = "CSCONTENT-" + uuid4().hex
    before_body = _body_text(page)
    _submit(page, prompt + "\n\nIdentificador desta solicitação: " + marker
            + ". Não inclua o identificador no JSON.")

    deadline = time.monotonic() + (timeout_seconds or legacy._timeout_seconds())
    last_candidate = ""
    last_observed = ""
    stable = 0
    valid_since = None
    while time.monotonic() < deadline:
        if legacy._looks_like_auth_wall(page) and legacy._composer(page, 1000) is None:
            raise legacy.ChatGPTPlaywrightError("Sessão ChatGPT expirou durante a geração da descrição.")
        current = _conversation_candidates(page, marker)
        if current:
            last_observed = "\n".join(current)
        candidate = next((text for text in reversed(current)
                          if _looks_like_content_json(text, expected)), "")
        if candidate:
            if candidate == last_candidate:
                stable += 1
            else:
                stable = 0
                valid_since = time.monotonic()
            last_candidate = candidate
            if stable >= 2 and (not _assistant_busy(page) or time.monotonic() - valid_since >= 8):
                if job:
                    legacy._update_job_state(str(job["job_id"]),
                        content_response_kind=response_kind(candidate, expected),
                        content_prompt_marker=marker)
                return candidate
        else:
            # A temporarily valid prefix must not survive a subsequently truncated
            # or replaced response, even if the timeout is about to expire.
            last_candidate = ""
            valid_since = None
            stable = 0
        time.sleep(0.7)

    kind = response_kind(last_observed, expected)
    if kind == "content_no_response":
        body = _body_text(page)
        # Full-page text is useful for diagnosing selector failures but cannot
        # establish identity/turn provenance, so it is never returned as content.
        if body != before_body and _looks_like_content_json(body, expected):
            kind = "content_selector_unproven"
    messages = {
        "content_no_response": "ChatGPT não apresentou resposta para a solicitação atual.",
        "content_response_partial": "ChatGPT respondeu parcialmente; o JSON está incompleto.",
        "content_json_invalid": "ChatGPT respondeu, mas o JSON permanece inválido após reparar a formatação do DOM.",
        "content_product_mismatch": "ChatGPT respondeu para outro produto; conteúdo descartado.",
        "content_selector_unproven": "Há JSON na página, mas o seletor não comprovou o turno da resposta atual.",
        "content_json_complete": "ChatGPT respondeu JSON completo, mas a resposta ainda não estabilizou.",
        "content_json_dom_repaired": "O JSON foi reparado após formatação do DOM, mas a resposta ainda não estabilizou.",
    }
    diagnostic = ""
    try:
        from app.additions import chatgpt_playwright_compat as compat
        diagnostic = compat._diagnostic(page, kind)
    except Exception:
        pass
    error = legacy.ChatGPTPlaywrightError(
        messages[kind] + (f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""))
    error.code = kind
    raise error


def _plain_url(value: Any) -> str:
    return clean_official_url(value) or str(value or "").strip()


def _htmlize(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if re.search(r"<(?:p|h[2-6]|ul|ol|li|strong|em|br)\b", raw, re.I):
        return raw
    normalized = re.sub(r"(?<=[.!?])(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", "\n\n", raw)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    chunks = [" ".join(part.split()) for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if len(chunks) == 1:
        sentences = re.split(r"(?<=[.!?])\s+", chunks[0])
        chunks = [" ".join(sentences[i : i + 3]).strip() for i in range(0, len(sentences), 3)]
    return "".join(f"<p>{chunk}</p>" for chunk in chunks if chunk)


def _legacy_parse(text: str, job: dict[str, Any]) -> dict[str, Any]:
    labels = ["TÍTULO", "BREVE DESCRIÇÃO", "DESCRIÇÃO", "TÍTULO SEO", "META DESCRIPTION", "TAGS", "CATEGORIA"]
    values = {label: legacy._legacy_section(text, label, labels[index + 1 :]) for index, label in enumerate(labels)}
    if not values["BREVE DESCRIÇÃO"] or not values["DESCRIÇÃO"]:
        raise legacy.ChatGPTPlaywrightError("Resposta do ChatGPT não contém JSON nem o bloco estruturado esperado.")
    result = {
        "product_name": values["TÍTULO"] or job.get("product_name"),
        "short_description": " ".join(values["BREVE DESCRIÇÃO"].split()),
        "content": _htmlize(values["DESCRIÇÃO"]),
        "categories": normalize_list(values["CATEGORIA"]),
        "tags": normalize_list(values["TAGS"]),
        "developer": clean_developer(job.get("developer")),
        "official_url": _plain_url(job.get("official_url")),
    }
    if not valid_content(result):
        raise legacy.ChatGPTPlaywrightError("ChatGPT retornou conteúdo incompleto ou curto demais para o cadastro.")
    return result


def parse_content_response(text: str, job: dict[str, Any]) -> dict[str, Any]:
    expected = str(job.get("product_name") or "")
    payload = _extract_json(text, expected)
    if not isinstance(payload, dict):
        if "{" in text:
            raise legacy.ChatGPTPlaywrightError("JSON incompleto ou identidade de outro produto/ausente; conteúdo descartado.")
        return _legacy_parse(text, job)

    # developer/official_url já foram confirmados pelo research service. Não
    # aceite que a renderização Markdown do ChatGPT corrompa esses metadados.
    job_developer = clean_developer(job.get("developer"))
    model_developer = clean_developer(payload.get("developer"))
    job_official = clean_official_url(job.get("official_url"))
    model_official = clean_official_url(payload.get("official_url"))

    result = {
        "product_name": str(payload.get("product_name") or payload.get("title") or "").strip(),
        "short_description": " ".join(str(payload.get("short_description") or "").split()),
        "content": _htmlize(str(payload.get("content") or payload.get("description") or "")),
        "categories": normalize_list(payload.get("categories") or payload.get("category") or []),
        "tags": normalize_list(payload.get("tags") or []),
        "developer": job_developer or model_developer,
        "official_url": job_official or model_official,
    }
    if not valid_content(result):
        raise legacy.ChatGPTPlaywrightError("ChatGPT retornou conteúdo incompleto ou curto demais para o cadastro.")
    return result


def _strict_prompt(job: dict[str, Any], correction: bool = False) -> str:
    prefix = (
        "A resposta anterior ficou fora do formato. Gere novamente sem explicar o erro.\n\n"
        if correction
        else ""
    )
    kind_label = "plugin" if str(job.get("kind") or "").casefold() == "plugin" else "tema"
    developer = clean_developer(job.get("developer")) or "não confirmado"
    official = clean_official_url(job.get("official_url")) or "não confirmada"
    source_url = clean_official_url(job.get("source_url")) or str(job.get("source_url") or "")

    return f"""{prefix}Você está cadastrando um {kind_label} WordPress na loja PluginTema, no projeto {legacy.project_name()}.
Produto: {job.get('product_name') or ''}
Versão: {job.get('source_version') or ''}
Fonte aprovada: {source_url}
Página oficial confirmada: {official}
Desenvolvedor confirmado: {developer}

Antes de redigir, use as páginas fornecidas como referência quando estiverem acessíveis. Não invente informação que não esteja confirmada.

REGRAS OBRIGATÓRIAS:
- short_description: 400 a 500 caracteres, 2 ou 3 frases, comercial e informativa, sem versão e sem HTML.
- content: HTML simples e legível, com pelo menos 2 <p>. Quando houver recursos confirmados, use <h2>Principais recursos</h2> e <ul><li>...</li></ul>.
- Evite texto genérico, repetitivo ou colado sem separação entre frases.
- categories e tags: somente termos realmente coerentes.
- developer e official_url: copie EXATAMENTE os valores confirmados acima; não reformate URL em Markdown.
- Use EXATAMENTE as chaves product_name, short_description, content, categories, tags, developer, official_url.
- Não escape underscores nas chaves.
- Não escreva explicações antes ou depois.

RESPONDA SOMENTE em um bloco de código JSON válido, neste formato:
```json
{{"product_name":"...","short_description":"...","content":"<p>...</p>","categories":[],"tags":[],"developer":"{developer}","official_url":"{official}"}}
```
"""


def _quality_ok(result: dict[str, Any]) -> bool:
    short = str(result.get("short_description") or "")
    content = str(result.get("content") or "")
    return bool(
        valid_content(result)
        and 320 <= len(short) <= 650
        and re.search(r"<p\b", content, re.I)
        and not re.search(r"\[[^\]]+\]\(https?://", str(result.get("official_url") or ""), re.I)
    )


def generate_content(job: dict[str, Any]) -> dict[str, Any]:
    with legacy._LOCK, legacy._browser() as page:
        legacy._open_job_conversation(page, str(job["job_id"]))
        last_error: Exception | None = None
        result: dict[str, Any] | None = None
        for attempt in range(2):
            text = _wait_content_response(page, _strict_prompt(job, correction=attempt > 0), job=job)
            try:
                result = parse_content_response(text, job)
                if _quality_ok(result):
                    break
                last_error = legacy.ChatGPTPlaywrightError(
                    "A descrição retornada não está no padrão comercial/HTML esperado."
                )
                result = None
            except Exception as error:
                last_error = error
                result = None
        if result is None:
            raise legacy.ChatGPTPlaywrightError(
                f"ChatGPT respondeu, mas a descrição não pôde ser normalizada após 2 tentativas: {last_error}"
            )

        legacy._update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            content_ready=True,
            content_fingerprint=legacy._content_fingerprint({**job, **result}),
            content_sha256=legacy.content_digest({**job, **result}),
            content_generated_at=int(time.time()),
        )
        return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    legacy.parse_content_response = parse_content_response
    legacy.generate_content = generate_content
    _INSTALLED = True


__all__ = [
    "generate_content",
    "install",
    "parse_content_response",
    "_conversation_candidates",
    "_extract_last_marked",
    "_htmlize",
    "_rendered_text",
]
