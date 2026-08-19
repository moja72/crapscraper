from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

import app.addition_chat1_official_resolution_policy as chat1
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_conversation_capture_policy as capture
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_parallel_generation_policy as parallel
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_DESCRIPTION_TIMEOUT_SECONDS = 120
_IMAGE_TIMEOUT_SECONDS = 240
_DESCRIPTION_POLL_SECONDS = 15
_IMAGE_POLL_SECONDS = 30


def _normalize_chat_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    except Exception:
        return raw.rstrip("/")


def _same_chat_url(left: str, right: str) -> bool:
    a = _normalize_chat_url(left)
    b = _normalize_chat_url(right)
    return bool(a and b and a == b)


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:
        return ""


def _bind_chat_page(
    context: Any,
    current: Any,
    chat_url: str,
    project_url: str,
    job_id: str,
    label: str,
) -> Any:
    target = str(chat_url or "").strip()
    if target:
        if reconnect._page_is_alive(current) and _same_chat_url(_page_url(current), target):
            return current
        for page in list(getattr(context, "pages", []) or []):
            try:
                if reconnect._page_is_alive(page) and _same_chat_url(_page_url(page), target):
                    return page
            except Exception:
                continue
        one_click._emit(
            job_id,
            f"{label}: a aba original não está disponível; reabrindo exatamente a conversa mapeada.",
            step="chatgpt",
        )
        page = context.new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=60_000)
        one_click._wait_composer(page, job_id, timeout_seconds=60)
        return page

    if reconnect._page_is_alive(current):
        return current
    page = reconnect._pick_page(context)
    return reconnect._ensure_project_page_resilient(
        context, page, job_id, project_url, timeout_seconds=60
    )


def _description_only_prompt(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    kind = parallel._kind(job)
    kind_label = "tema WordPress" if kind == "theme" else "plugin WordPress"
    marketplace = parallel._expected_marketplace(job)
    example = (
        "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
        "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress "
        "mais modernos e profissionais. Ele funciona com edição de arrastar e soltar, widgets premium, templates e "
        "construtores para tema, formulários e pop-ups, deixando a criação mais prática e reduzindo dependência de código no projeto."
    )
    return f"""Pesquise e escreva SOMENTE a breve descrição comercial deste produto para o e-commerce PluginTema.

PRODUTO
Nome: {name}
Tipo: {kind_label}
Versão de referência: {job.get('source_version') or '-'}
Marketplace/fonte oficial esperada: {marketplace}

PESQUISA
Localize por pesquisa web o produto EXATO no marketplace/site oficial esperado e confirme que o nome corresponde ao produto. Use a fonte oficial e, quando necessário, snippets/resultados públicos acessíveis para entender finalidade, recursos confirmados, público e posicionamento. Não use sites de redistribuição como fonte principal e não invente recursos.

DESCRIÇÃO
Escreva um único parágrafo em português do Brasil, com aproximadamente 400 a 500 caracteres e 2 ou 3 frases. Comece pelo principal benefício, mencione o produto naturalmente, explique o que ele ajuda a fazer e finalize indicando para quais projetos ou usuários ele é útil. Não inclua a versão.

Use apenas estrutura, ritmo e extensão deste exemplo como referência; não copie o conteúdo:
"{example}"

REGRA DE SAÍDA
Responda SOMENTE com o parágrafo final da descrição. Não mostre URL, página oficial, título oficial, fontes, rótulos, Markdown, SEO, tags, categoria ou explicações."""


def _description_candidates(page: Any) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    sources: list[str] = []
    try:
        sources.extend(capture._assistant_text_candidates(page))
    except Exception:
        pass
    try:
        sources.extend(chat1._assistant_texts_fallback(page))
    except Exception:
        pass
    for raw in sources:
        candidate = final_validation._validated_description(str(raw or ""))
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        values.append(candidate)
    values.sort(key=lambda value: abs(len(value) - 450))
    return values


def _valid_existing_description(job: Mapping[str, Any]) -> str:
    return final_validation._validated_description(str(job.get("short_description") or ""))


def _assistant_image_candidates(page: Any, before: set[str]) -> list[dict[str, Any]]:
    rows = []
    for item in capture._image_candidates(page):
        source = str(item.get("src") or "")
        if not source or source in before:
            continue
        if capture._image_candidate_score(item) < 0:
            continue
        rows.append(dict(item))
    rows.sort(key=capture._image_candidate_score, reverse=True)
    return rows


def _element_image_data_url(page: Any, candidate: Mapping[str, Any], reference_sha: str) -> str:
    try:
        index = int(candidate.get("index"))
    except Exception:
        return ""
    try:
        locator = page.locator("img").nth(index)
        if not locator.count() or not locator.is_visible():
            return ""
        raw = locator.screenshot(type="png")
    except Exception:
        return ""
    if not raw or len(raw) < 20_000:
        return ""
    current_sha = hashlib.sha256(raw).hexdigest()
    if reference_sha and current_sha == reference_sha:
        return ""
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _image_data_url(page: Any, before: set[str], reference_sha: str) -> str:
    if simple._assistant_busy(page):
        return ""
    for candidate in _assistant_image_candidates(page, before)[:6]:
        source = str(candidate.get("src") or "")
        data_url = capture._extract_image_data_url(page, source)
        raw = capture._decode_data_url(data_url)
        if len(raw) >= 20_000:
            current_sha = hashlib.sha256(raw).hexdigest()
            if not reference_sha or current_sha != reference_sha:
                return data_url
        rendered = _element_image_data_url(page, candidate, reference_sha)
        if rendered:
            return rendered
    return ""


def _persist_description(job_id: str, description: str) -> dict[str, Any]:
    result = capture._save_description_tracked(job_id, description)
    one_click._emit(
        job_id,
        f"Chat 1 concluído: descrição capturada na conversa correta e salva ({len(description)} caracteres).",
        step="description_ready",
        progress=40,
    )
    return result


def _persist_image(job_id: str, data_url: str) -> dict[str, Any]:
    image_path = one_click._persist_image(job_id, data_url)
    raw = capture._decode_data_url(data_url)
    if raw:
        try:
            additions._update(job_id, image_sha256=hashlib.sha256(raw).hexdigest(), error="")
        except Exception:
            pass
    one_click._emit(
        job_id,
        f"Chat 2 concluído: imagem capturada na conversa correta e salva em {Path(image_path).name}.",
        step="image_ready",
        progress=78,
    )
    return additions._row(job_id)


def _run_bound_parallel_chats(job_id: str) -> dict[str, Any]:
    capture._ensure_tracking_schema()
    job = additions._row(job_id)
    reference = creative._reference_path(job)
    if not reference.exists():
        raise RuntimeError(
            f"Referência visual obrigatória não encontrada em {reference}. Confirme Exemplo Plugin.webp e Exemplo Tema.webp em app/static."
        )

    description_ready = bool(_valid_existing_description(job))
    image_ready = bool(parallel._valid_existing_image(job_id, job))
    if description_ready:
        one_click._emit(job_id, "A descrição validada já existe; o Chat 1 será reaproveitado.", step="description_ready", progress=40)
    if image_ready:
        one_click._emit(job_id, "A imagem final validada já existe; o Chat 2 será reaproveitado.", step="image_ready", progress=78)
    if description_ready and image_ready:
        return additions._row(job_id)

    project_url = coproducao._project_url()
    endpoint, profile_dir = cdp._ensure_debug_browser(project_url)
    one_click._emit(job_id, f"Chrome conectado via CDP. Perfil: {profile_dir.name}.", step="chatgpt", progress=8)
    coproducao._wait_login_then_project(job_id, endpoint, project_url)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}") from None

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError("Chrome autenticado, mas nenhum contexto de navegação foi encontrado.")
        context = contexts[0]
        base_page = reconnect._pick_page(context)
        description_page = None
        image_page = None
        description_started = 0.0
        image_started = 0.0
        next_description_log = float(_DESCRIPTION_POLL_SECONDS)
        next_image_log = float(_IMAGE_POLL_SECONDS)
        image_before: set[str] = set()
        fallback_sent = False
        official_capture: Path | None = None

        one_click._emit(
            job_id,
            "Abrindo os dois chats em paralelo. Cada etapa será lida exclusivamente pela URL da sua própria conversa.",
            step="chatgpt",
            progress=10,
        )

        if not description_ready:
            description_page = simple._fresh_project_chat(context, base_page, job_id, project_url, "Chat 1/2 — descrição")
            one_click._emit(job_id, "Chat 1/2: enviando somente o pedido da breve descrição.", step="chatgpt_description", progress=15)
            description_page, _before_count, _before_images = reconnect._send_message_resilient(
                context, description_page, _description_only_prompt(additions._row(job_id)), job_id, project_url
            )
            description_started = time.time()

        if not image_ready:
            image_page = context.new_page()
            image_page = simple._fresh_project_chat(context, image_page, job_id, project_url, "Chat 2/2 — imagem")
            one_click._emit(
                job_id,
                f"Chat 2/2: anexando {reference.name} e iniciando a geração sem esperar o Chat 1 terminar.",
                step="chatgpt_image",
                progress=50,
            )
            if not creative._attach_reference(image_page, reference, job_id):
                raise RuntimeError(f"Não foi possível anexar a referência visual obrigatória {reference.name}.")
            image_page, _image_count, image_before = reconnect._send_message_resilient(
                context, image_page, parallel._parallel_image_prompt(additions._row(job_id)), job_id, project_url
            )
            image_started = time.time()

        one_click._emit(
            job_id,
            "Chats enviados. Monitoramento por conversa ativo: descrição a cada 15s e imagem a cada 30s.",
            step="chatgpt",
            progress=22,
        )
        _reference, reference_sha = final_validation._reference_hash(job_id)

        while not (description_ready and image_ready):
            now = time.time()
            job = additions._row(job_id)

            if not description_ready and description_page is not None:
                chat_url = str(job.get("description_chat_url") or "")
                description_page = _bind_chat_page(
                    context, description_page, chat_url, project_url, job_id, "Chat 1"
                )
                candidates = _description_candidates(description_page)
                if candidates and not simple._assistant_busy(description_page):
                    _persist_description(job_id, candidates[0])
                    description_ready = True
                    job = additions._row(job_id)
                else:
                    elapsed = now - description_started
                    if elapsed >= _DESCRIPTION_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 1 exibiu a descrição, mas ela não pôde ser capturada na conversa mapeada dentro de 2 minutos."
                        )
                    if elapsed >= next_description_log:
                        one_click._emit(
                            job_id,
                            f"Chat 1 ainda processando; conferindo especificamente {chat_url or 'a conversa mapeada'} ({int(elapsed)}s/120s).",
                            step="chatgpt_description",
                            progress=24,
                        )
                        next_description_log += _DESCRIPTION_POLL_SECONDS

            if not image_ready and image_page is not None:
                chat_url = str(job.get("image_chat_url") or "")
                image_page = _bind_chat_page(
                    context, image_page, chat_url, project_url, job_id, "Chat 2"
                )
                data_url = _image_data_url(image_page, image_before, reference_sha)
                if data_url:
                    _persist_image(job_id, data_url)
                    image_ready = True
                else:
                    refusal = parallel._assistant_refusal_text(image_page)
                    if refusal and not fallback_sent and not simple._assistant_busy(image_page):
                        fallback_sent = True
                        current_job = additions._row(job_id)
                        official_url = str(current_job.get("source_official_url") or "")
                        if official_url:
                            official_capture = parallel._capture_official_visual(context, job_id, official_url)
                            if official_capture is not None:
                                one_click._emit(
                                    job_id,
                                    "Chat 2 recusou o acesso direto à página oficial; anexando captura local e reenviando sem depender da URL.",
                                    step="chatgpt_image",
                                    progress=66,
                                )
                                creative._attach_reference(image_page, official_capture, job_id)
                        image_before.update(str(item.get("src") or "") for item in capture._image_candidates(image_page))
                        image_page, _fallback_count, fallback_before = reconnect._send_message_resilient(
                            context,
                            image_page,
                            parallel._fallback_image_prompt(current_job, has_official_capture=official_capture is not None),
                            job_id,
                            project_url,
                        )
                        image_before.update(fallback_before)
                        one_click._emit(
                            job_id,
                            "Fallback do Chat 2 enviado; continuando a capturar somente a conversa de imagem.",
                            step="chatgpt_image",
                            progress=67,
                        )

                    elapsed = now - image_started
                    if elapsed >= _IMAGE_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 2 não entregou uma imagem final capturável na conversa mapeada dentro de 4 minutos."
                        )
                    if elapsed >= next_image_log:
                        one_click._emit(
                            job_id,
                            f"Chat 2 ainda processando; conferindo especificamente {chat_url or 'a conversa mapeada'} ({int(elapsed)}s/240s).",
                            step="chatgpt_image",
                            progress=68,
                        )
                        next_image_log += _IMAGE_POLL_SECONDS

            time.sleep(0.8)

    return additions._row(job_id)


def install_addition_chat_binding_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    simple._run_two_chats = _run_bound_parallel_chats
    _INSTALLED = True
