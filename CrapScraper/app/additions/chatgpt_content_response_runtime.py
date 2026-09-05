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
    text = str(value or "")
    text = re.sub(r"\\([_<>])", r"\1", text)
    return text


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


def _conversation_candidates(page: Any) -> list[str]:
    """Lê respostas sem depender de um único atributo do DOM.

    Adaptado do leitor resiliente da versão legada: tenta assistant-role,
    conversation-turn, article/prose e blocos de código, rejeitando turnos
    explicitamente marcados como user.
    """
    try:
        rows = page.evaluate(
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

              document.querySelectorAll('main pre code').forEach(node => push(node, 'code'));
              document.querySelectorAll('[data-message-author-role="assistant"]').forEach(
                node => push(node, 'assistant-role')
              );
              document.querySelectorAll('main [data-testid^="conversation-turn-"]').forEach(turn => {
                const roleNode = turn.matches('[data-message-author-role]')
                  ? turn : turn.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (role === 'user') return;
                const preferred =
                  turn.querySelector('pre code') ||
                  turn.querySelector('[data-message-author-role="assistant"]') ||
                  turn.querySelector('.markdown') ||
                  turn.querySelector('[class*="markdown"]') ||
                  turn.querySelector('[class*="prose"]') ||
                  turn;
                push(preferred, 'conversation-turn');
              });
              document.querySelectorAll('main article').forEach(article => {
                const roleNode = article.matches('[data-message-author-role]')
                  ? article : article.querySelector('[data-message-author-role]');
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                if (role === 'user') return;
                const preferred =
                  article.querySelector('pre code') ||
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

    values: list[str] = []
    for row in rows or []:
        if isinstance(row, Mapping):
            text = _rendered_text(row.get("text") or "").strip()
        else:
            text = _rendered_text(row).strip()
        if text:
            values.append(text)
    return values


def _repair_json_candidate(candidate: str) -> str:
    text = str(candidate or "").strip().strip("`").strip()
    text = re.sub(r"\\([_<>])", r"\1", text)
    return text


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = _rendered_text(text).strip()
    marked = _extract_last_marked(raw)
    if marked:
        raw = marked
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.I | re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(_repair_json_candidate(candidate))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _looks_like_content_json(text: str) -> bool:
    payload = _extract_json(text)
    if not isinstance(payload, dict):
        return False
    keys = {str(key).replace("\\_", "_") for key in payload}
    return "short_description" in keys and bool(keys & {"content", "description"})


def _wait_content_response(page: Any, prompt: str, timeout_seconds: int | None = None) -> str:
    before_candidates = set(_conversation_candidates(page))
    before_body = _body_text(page)
    before_end_count = before_body.count(_END)
    _submit(page, prompt)

    deadline = time.monotonic() + (timeout_seconds or legacy._timeout_seconds())
    last_candidate = ""
    stable = 0
    first_valid_at: float | None = None

    while time.monotonic() < deadline:
        if legacy._looks_like_auth_wall(page) and legacy._composer(page, 1000) is None:
            raise legacy.ChatGPTPlaywrightError(
                "Sessão ChatGPT expirou durante a geração da descrição. Execute o bootstrap novamente."
            )

        # Caminho principal: resposta nova detectada pelos turnos/code blocks.
        current = _conversation_candidates(page)
        fresh = [text for text in current if text not in before_candidates]
        candidate = ""
        for text in reversed(fresh):
            if _looks_like_content_json(text):
                candidate = text
                break

        # Compatibilidade com o envelope usado nas tentativas anteriores.
        if not candidate:
            body = _body_text(page)
            if body.count(_END) >= before_end_count + 2:
                marked = _extract_last_marked(body)
                if marked and _looks_like_content_json(marked):
                    candidate = marked

        if candidate:
            if first_valid_at is None:
                first_valid_at = time.monotonic()
            if candidate == last_candidate:
                stable += 1
            else:
                last_candidate = candidate
                stable = 0

            # Não espere minutos por um botão Stop obsoleto: depois que existe
            # JSON completo e estável, dê no máximo alguns segundos à UI.
            grace_elapsed = time.monotonic() - first_valid_at
            if stable >= 2 and (not _assistant_busy(page) or grace_elapsed >= 8):
                return candidate

        time.sleep(0.7)

    # Se havia JSON válido completo perto do timeout, prefira utilizá-lo a
    # transformar uma resposta pronta em erro de tempo limite.
    if last_candidate and _looks_like_content_json(last_candidate):
        return last_candidate

    diagnostic = ""
    try:
        from app.additions import chatgpt_playwright_compat as compat

        diagnostic = compat._diagnostic(page, "content_response_timeout")
    except Exception:
        pass
    suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
    raise legacy.ChatGPTPlaywrightError(
        "O ChatGPT exibiu a descrição, mas o CrapScraper não conseguiu localizar um JSON completo na resposta."
        + suffix
    )


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
    payload = _extract_json(text)
    if not isinstance(payload, dict):
        return _legacy_parse(text, job)

    # developer/official_url já foram confirmados pelo research service. Não
    # aceite que a renderização Markdown do ChatGPT corrompa esses metadados.
    job_developer = clean_developer(job.get("developer"))
    model_developer = clean_developer(payload.get("developer"))
    job_official = clean_official_url(job.get("official_url"))
    model_official = clean_official_url(payload.get("official_url"))

    result = {
        "product_name": str(payload.get("product_name") or payload.get("title") or job.get("product_name") or "").strip(),
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
            text = _wait_content_response(page, _strict_prompt(job, correction=attempt > 0))
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
