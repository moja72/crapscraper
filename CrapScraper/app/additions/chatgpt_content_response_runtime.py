from __future__ import annotations

import json
import re
import time
from typing import Any

from app.additions import chatgpt_playwright as legacy
from app.additions.content import normalize_list, valid_content

_BEGIN = "<<<CRAPSCRAPER_JSON_BEGIN>>>"
_END = "<<<CRAPSCRAPER_JSON_END>>>"
_INSTALLED = False


def _body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=3000) or "")
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


def _extract_last_marked(text: str) -> str:
    raw = str(text or "")
    end = raw.rfind(_END)
    if end < 0:
        return ""
    begin = raw.rfind(_BEGIN, 0, end)
    if begin < 0:
        return ""
    return raw[begin + len(_BEGIN) : end].strip().strip("`").strip()


def _assistant_fallback(page: Any) -> str:
    selectors = (
        "[data-message-author-role='assistant']",
        "article[data-testid^='conversation-turn-']",
        "[data-testid^='conversation-turn-']",
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue
        for index in range(max(0, count - 12), count):
            try:
                text = str(locator.nth(index).inner_text(timeout=1500) or "").strip()
            except Exception:
                continue
            key = text[-600:]
            if not text or key in seen:
                continue
            seen.add(key)
            lowered = text.casefold()
            if "regras obrigatórias" in lowered or "responda exatamente neste envelope" in lowered:
                continue
            # Fallback para mudanças futuras no DOM: aceite apenas uma resposta
            # que pareça efetivamente um objeto JSON, não o prompt do usuário.
            if (
                "{" in text
                and "}" in text
                and ('"short_description"' in text or '"short\\_description"' in text)
                and ('"content"' in text or '"description"' in text)
            ):
                candidates.append(text)
    return candidates[-1] if candidates else ""


def _wait_content_response(page: Any, prompt: str, timeout_seconds: int | None = None) -> str:
    before_body = _body_text(page)
    before_end_count = before_body.count(_END)
    _submit(page, prompt)
    deadline = time.monotonic() + (timeout_seconds or legacy._timeout_seconds())
    last_fallback = ""
    stable_fallback = 0

    while time.monotonic() < deadline:
        if legacy._looks_like_auth_wall(page) and legacy._composer(page, 1000) is None:
            raise legacy.ChatGPTPlaywrightError(
                "Sessão ChatGPT expirou durante a geração da descrição. Execute o bootstrap novamente."
            )

        body = _body_text(page)
        # O prompt do usuário contém os delimitadores uma vez; quando a resposta
        # fecha o envelope, existe uma segunda ocorrência. Assim não dependemos
        # de data-message-author-role, que muda com frequência na UI do ChatGPT.
        if body.count(_END) >= before_end_count + 2:
            marked = _extract_last_marked(body)
            if marked:
                return marked

        fallback = _assistant_fallback(page)
        if fallback:
            if fallback == last_fallback and not legacy._stop_visible(page):
                stable_fallback += 1
            else:
                stable_fallback = 0
                last_fallback = fallback
            if stable_fallback >= 3:
                return fallback
        time.sleep(0.8)

    diagnostic = ""
    try:
        from app.additions import chatgpt_playwright_compat as compat

        diagnostic = compat._diagnostic(page, "content_response_timeout")
    except Exception:
        pass
    suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
    raise legacy.ChatGPTPlaywrightError(
        "O ChatGPT exibiu a descrição, mas o CrapScraper não conseguiu confirmar o fim da resposta."
        + suffix
    )


def _repair_json_candidate(candidate: str) -> str:
    text = str(candidate or "").strip().strip("`").strip()
    # A camada visual do ChatGPT pode devolver escapes Markdown em underscores,
    # como product\_name. Esse escape é inválido em JSON e deve ser removido.
    text = re.sub(r"\\([_<>])", r"\1", text)
    return text


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
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


def _plain_url(value: Any) -> str:
    text = str(value or "").strip()
    markdown = re.search(r"\[[^\]]*\]\((https?://[^)]+)\)", text, re.I)
    if markdown:
        return markdown.group(1).strip()
    match = re.search(r"https?://[^\s<>\]]+", text, re.I)
    return match.group(0).rstrip(").,;") if match else text


def _htmlize(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if re.search(r"<(?:p|h[2-6]|ul|ol|li|strong|em|br)\b", raw, re.I):
        return raw
    # Último fallback: nunca publique o bloco corrido observado no teste real.
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
        "developer": job.get("developer") or "",
        "official_url": _plain_url(job.get("official_url") or ""),
    }
    if not valid_content(result):
        raise legacy.ChatGPTPlaywrightError("ChatGPT retornou conteúdo incompleto ou curto demais para o cadastro.")
    return result


def parse_content_response(text: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = _extract_json(text)
    if not isinstance(payload, dict):
        return _legacy_parse(text, job)

    result = {
        "product_name": str(payload.get("product_name") or payload.get("title") or job.get("product_name") or "").strip(),
        "short_description": " ".join(str(payload.get("short_description") or "").split()),
        "content": _htmlize(str(payload.get("content") or payload.get("description") or "")),
        "categories": normalize_list(payload.get("categories") or payload.get("category") or []),
        "tags": normalize_list(payload.get("tags") or []),
        "developer": str(payload.get("developer") or job.get("developer") or "").strip(),
        "official_url": _plain_url(payload.get("official_url") or job.get("official_url") or ""),
    }
    if not valid_content(result):
        raise legacy.ChatGPTPlaywrightError("ChatGPT retornou conteúdo incompleto ou curto demais para o cadastro.")
    return result


def _strict_prompt(job: dict[str, Any], correction: bool = False) -> str:
    prefix = (
        "A resposta anterior não cumpriu integralmente o formato. Corrija-a agora sem repetir a explicação.\n\n"
        if correction
        else ""
    )
    kind_label = "plugin" if str(job.get("kind") or "").casefold() == "plugin" else "tema"
    return f"""{prefix}Você está cadastrando um {kind_label} WordPress na loja PluginTema dentro do projeto {legacy.project_name()}.
Produto: {job.get('product_name') or ''}
Versão: {job.get('source_version') or ''}
Fonte aprovada: {job.get('source_url') or ''}
Página oficial confirmada: {job.get('official_url') or 'não confirmada'}
Desenvolvedor confirmado: {job.get('developer') or 'não confirmado'}

REGRAS OBRIGATÓRIAS:
- Não invente recursos, compatibilidades, desenvolvedor, URL ou benefício não confirmado.
- short_description: 400 a 500 caracteres, texto corrido comercial/informativo, sem versão e sem HTML.
- content: HTML simples e legível. Use pelo menos 2 <p>. Se houver recursos confirmados, use <h2>Principais recursos</h2> e <ul><li>...</li></ul>.
- categories e tags: somente termos realmente coerentes.
- official_url: URL pura, sem Markdown, colchetes ou link formatado.
- Use EXATAMENTE as chaves product_name, short_description, content, categories, tags, developer, official_url.
- Não escape underscores nas chaves. Escreva product_name, nunca product\\_name.
- Não escreva explicações antes ou depois do objeto.

Responda EXATAMENTE neste envelope, sem bloco de código:
{_BEGIN}
JSON válido com as sete chaves solicitadas
{_END}
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
    "_extract_last_marked",
    "_htmlize",
]
