from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Mapping

import app.addition_chat1_official_resolution_policy as chat1
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_conversation_capture_policy as capture
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_DESCRIPTION_TIMEOUT_SECONDS = 120
_IMAGE_TIMEOUT_SECONDS = 240
_DESCRIPTION_POLL_SECONDS = 15
_IMAGE_POLL_SECONDS = 30

_IMAGE_REFUSAL_MARKERS = (
    "não consigo gerar esta imagem",
    "nao consigo gerar esta imagem",
    "não pôde ser acessada com sucesso",
    "nao pode ser acessada com sucesso",
    "envie capturas da página oficial",
    "envie capturas da pagina oficial",
    "outra url oficial acessível",
    "outra url oficial acessivel",
    "i can't generate this image",
    "i cannot generate this image",
    "could not access the official page",
    "couldn't access the official page",
    "send screenshots of the official page",
)

_BLOCKED_PAGE_MARKERS = (
    "access denied",
    "forbidden",
    "verify you are human",
    "checking your browser",
    "captcha",
    "cloudflare ray id",
)


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _expected_marketplace(job: Mapping[str, Any]) -> str:
    marketplace = chat1._marketplace(job)
    return {"themeforest": "ThemeForest", "codecanyon": "CodeCanyon"}.get(
        marketplace,
        "site oficial do desenvolvedor ou marketplace oficial",
    )


def _valid_existing_description(job: Mapping[str, Any]) -> str:
    official = str(job.get("source_official_url") or "").strip()
    description = final_validation._validated_description(str(job.get("short_description") or ""))
    if not description or not chat1._valid_official(job, official):
        return ""
    return description


def _valid_existing_image(job_id: str, job: Mapping[str, Any]) -> str:
    image_path = Path(str(job.get("image_path") or ""))
    if not image_path.exists() or not image_path.is_file():
        return ""
    try:
        final_validation._validate_image_file(job_id, image_path)
    except Exception:
        return ""
    return str(image_path)


def _parallel_image_prompt(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    kind = _kind(job)
    kind_label = "tema WordPress" if kind == "theme" else "plugin WordPress"
    marketplace = _expected_marketplace(job)
    official = str(job.get("source_official_url") or "").strip()
    official_line = (
        f"Página oficial já identificada: {official}\n"
        if official and chat1._valid_official(job, official)
        else ""
    )

    if kind == "theme":
        visual = """TEMA — COMPOSIÇÃO
- O arquivo anexado 'exemplo tema.webp' define SOMENTE o tipo de mockup, proporções e acabamento.
- Gere uma NOVA imagem 1:1 com fundo totalmente transparente.
- Mostre um monitor Apple e um celular inteiros, com as duas telas claramente visíveis.
- Nas telas, represente a identidade visual real do tema pesquisado: marca/nome, cores e aparência compatíveis com screenshots ou imagens públicas encontradas para o produto.
- A posição do celular pode variar. Não reutilize as telas nem a marca da imagem de referência."""
    else:
        visual = """PLUGIN — COMPOSIÇÃO
- O arquivo anexado 'exemplo plugin.webp' define SOMENTE a caixa 3D, proporções e acabamento.
- Gere uma NOVA imagem 1:1 com fundo totalmente transparente e pelo menos 3 faces da caixa visíveis.
- Use o nome, cores e identidade visual real do plugin encontrada na pesquisa pública. Só use logotipo quando ele puder ser confirmado; não invente logo.
- Use fonte Quicksand e mostre exatamente: “Vitalício | Ilimitado | Atualizado”.
- Não reutilize a marca ou os textos da imagem de referência."""

    return f"""Gere SOMENTE a imagem principal deste produto para o e-commerce PluginTema. Não responda com texto fora da geração da imagem.

PRODUTO
Nome: {name}
Tipo: {kind_label}
Marketplace/fonte oficial esperada: {marketplace}
{official_line}
PESQUISA VISUAL
Pesquise o produto EXATO pelo nome acima e confirme a identidade no marketplace/site oficial esperado. Use resultados de busca, snippets, previews e imagens públicas acessíveis para reconhecer marca, cores, screenshots e aparência do produto.

IMPORTANTE SOBRE ACESSO
A geração NÃO depende de conseguir abrir diretamente a página oficial. Se a página oficial bloquear o acesso, estiver indisponível ou exigir proteção adicional, NÃO recuse a geração, NÃO peça capturas ao usuário e NÃO pare. Continue usando os resultados de busca, previews e referências públicas acessíveis que correspondam ao produto exato.

{visual}

REQUISITOS FINAIS
- Imagem quadrada 1:1.
- Fundo totalmente transparente, inclusive bordas e áreas vazias.
- Acabamento profissional para capa de produto em e-commerce.
- Não use cenário ou fundo sólido.
- Não corte os dispositivos ou a caixa.
- Não reutilize o arquivo anexado como resultado final.
- Não invente uma identidade visual contraditória com o produto pesquisado.
- Entregue uma única imagem final e aguarde a geração terminar completamente."""


def _fallback_image_prompt(job: Mapping[str, Any], *, has_official_capture: bool) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    official = str(job.get("source_official_url") or "").strip()
    capture_note = (
        "Também foi anexada uma captura local da página oficial; use-a como evidência visual do produto."
        if has_official_capture
        else "Use os resultados públicos de pesquisa já encontrados para confirmar a identidade visual."
    )
    return f"""Prossiga com a geração da imagem. Não responda com explicações e não peça arquivos adicionais.

Produto: {name}
Página oficial identificada: {official or 'use a pesquisa pelo nome do produto'}

A página oficial pode bloquear acesso automatizado. NÃO tente condicionar a tarefa à abertura direta dessa URL. {capture_note}
O arquivo de mockup já anexado continua sendo apenas referência de composição. Gere agora uma NOVA imagem final do produto, 1:1, profissional e com fundo transparente, seguindo as regras visuais do pedido anterior.

Se a URL oficial não abrir, use o nome exato do produto, o marketplace identificado, snippets, previews e imagens públicas acessíveis. NÃO recuse a geração e NÃO responda com texto: gere a imagem."""


def _assistant_refusal_text(page: Any) -> str:
    candidates: list[str] = []
    try:
        candidates.extend(chat1._assistant_texts_fallback(page))
    except Exception:
        pass
    for text in reversed(candidates[-8:]):
        lowered = str(text or "").lower()
        if any(marker in lowered for marker in _IMAGE_REFUSAL_MARKERS):
            return str(text or "").strip()
    return ""


def _generated_image_data_url(page: Any, before: set[str], reference_sha: str) -> str:
    if simple._assistant_busy(page):
        return ""
    candidates = [
        item
        for item in capture._image_candidates(page)
        if str(item.get("src") or "") not in before and capture._image_candidate_score(item) >= 0
    ]
    candidates.sort(key=capture._image_candidate_score, reverse=True)
    for candidate in candidates[:5]:
        source = str(candidate.get("src") or "")
        data_url = capture._extract_image_data_url(page, source)
        raw = capture._decode_data_url(data_url)
        if len(raw) < 20_000:
            continue
        current_sha = hashlib.sha256(raw).hexdigest()
        if reference_sha and current_sha == reference_sha:
            continue
        return data_url
    return ""


def _capture_official_visual(context: Any, job_id: str, official_url: str) -> Path | None:
    if not official_url:
        return None
    page = None
    try:
        page = context.new_page()
        page.goto(official_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)
        body = str(page.locator("body").inner_text(timeout=2500) or "").lower()
        if any(marker in body for marker in _BLOCKED_PAGE_MARKERS):
            return None
        target_dir = Path(__file__).resolve().parent.parent / "data" / "addition_official_assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{job_id}-official.png"
        page.screenshot(path=str(target), full_page=False)
        if not target.exists() or target.stat().st_size < 15_000:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return target
    except Exception:
        return None
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass


def _recover_page(context: Any, current: Any, chat_url: str, project_url: str, job_id: str) -> Any:
    if reconnect._page_is_alive(current):
        return current
    for page in list(getattr(context, "pages", []) or []):
        try:
            if chat_url and str(page.url or "") == chat_url and reconnect._page_is_alive(page):
                return page
        except Exception:
            continue
    page = context.new_page()
    target = chat_url or project_url
    page.goto(target, wait_until="domcontentloaded", timeout=60_000)
    return reconnect._ensure_project_page_resilient(context, page, job_id, project_url, timeout_seconds=60)


def _persist_description(job_id: str, official: str, official_title: str, description: str) -> dict[str, Any]:
    additions._update(job_id, source_official_url=official, error="")
    result = capture._save_description_tracked(job_id, description)
    one_click._emit(
        job_id,
        f"Chat 1 concluído em paralelo: página oficial confirmada ({official_title}) e descrição salva ({len(description)} caracteres).",
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
        f"Chat 2 concluído em paralelo: imagem final capturada e salva em {Path(image_path).name}.",
        step="image_ready",
        progress=78,
    )
    return additions._row(job_id)


def _run_parallel_chats(job_id: str) -> dict[str, Any]:
    capture._ensure_tracking_schema()
    job = additions._row(job_id)
    reference = creative._reference_path(job)
    if not reference.exists():
        raise RuntimeError(
            f"Referência visual obrigatória não encontrada em {reference}. "
            "Confirme Exemplo Plugin.webp e Exemplo Tema.webp em app/static."
        )

    description_ready = bool(_valid_existing_description(job))
    image_ready = bool(_valid_existing_image(job_id, job))
    if description_ready:
        one_click._emit(
            job_id,
            "A descrição e a página oficial já estavam validadas de uma tentativa anterior; o Chat 1 será reaproveitado.",
            step="description_ready",
            progress=40,
        )
    if image_ready:
        one_click._emit(
            job_id,
            "A imagem final validada já existe localmente; o Chat 2 será reaproveitado.",
            step="image_ready",
            progress=78,
        )
    if description_ready and image_ready:
        return additions._row(job_id)

    project_url = coproducao._project_url()
    endpoint, profile_dir = cdp._ensure_debug_browser(project_url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=8,
    )
    coproducao._wait_login_then_project(job_id, endpoint, project_url)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

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
            "Abrindo e enviando os dois chats antes de iniciar a espera: descrição e imagem serão processadas em paralelo.",
            step="chatgpt",
            progress=10,
        )

        if not description_ready:
            description_page = simple._fresh_project_chat(
                context, base_page, job_id, project_url, "Chat 1/2 — descrição"
            )
            description_prompt = chat1._description_prompt(additions._row(job_id))
            one_click._emit(
                job_id,
                "Chat 1/2: enviando pesquisa oficial + breve descrição.",
                step="chatgpt_description",
                progress=15,
            )
            description_page, _before_count, _before_images = reconnect._send_message_resilient(
                context, description_page, description_prompt, job_id, project_url
            )
            description_started = time.time()

        if not image_ready:
            try:
                image_page = context.new_page()
            except Exception:
                image_page = reconnect._pick_page(context)
            image_page = simple._fresh_project_chat(
                context, image_page, job_id, project_url, "Chat 2/2 — imagem"
            )
            one_click._emit(
                job_id,
                f"Chat 2/2: anexando {reference.name} e iniciando a geração sem esperar o Chat 1 terminar.",
                step="chatgpt_image",
                progress=50,
            )
            if not creative._attach_reference(image_page, reference, job_id):
                raise RuntimeError(f"Não foi possível anexar a referência visual obrigatória {reference.name}.")
            image_page, _image_count, image_before = reconnect._send_message_resilient(
                context,
                image_page,
                _parallel_image_prompt(additions._row(job_id)),
                job_id,
                project_url,
            )
            image_started = time.time()

        one_click._emit(
            job_id,
            "Chats enviados. Monitoramento paralelo ativo: descrição a cada 15s (até 2 min) e imagem a cada 30s (até 4 min).",
            step="chatgpt",
            progress=22,
        )

        _reference, reference_sha = final_validation._reference_hash(job_id)

        while not (description_ready and image_ready):
            now = time.time()
            job = additions._row(job_id)

            if not description_ready and description_page is not None:
                chat_url = str(job.get("description_chat_url") or "")
                description_page = _recover_page(
                    context, description_page, chat_url, project_url, job_id
                )
                found = None
                for raw in reversed(chat1._assistant_texts_fallback(description_page)):
                    official, official_title, description = chat1._parse_answer_parts(raw, job)
                    if official and description:
                        found = (official, official_title, description)
                        break
                if found and not simple._assistant_busy(description_page):
                    official, official_title, description = found
                    _persist_description(job_id, official, official_title or "título confirmado pela URL", description)
                    description_ready = True
                    job = additions._row(job_id)
                else:
                    elapsed = now - description_started
                    if elapsed >= _DESCRIPTION_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 1 não entregou página oficial + descrição válidas dentro de 2 minutos."
                        )
                    if elapsed >= next_description_log:
                        one_click._emit(
                            job_id,
                            f"Chat 1 ainda processando; nova conferência automática ({int(elapsed)}s/{_DESCRIPTION_TIMEOUT_SECONDS}s).",
                            step="chatgpt_description",
                            progress=24,
                        )
                        next_description_log += _DESCRIPTION_POLL_SECONDS

            if not image_ready and image_page is not None:
                chat_url = str(job.get("image_chat_url") or "")
                image_page = _recover_page(context, image_page, chat_url, project_url, job_id)
                data_url = _generated_image_data_url(image_page, image_before, reference_sha)
                if data_url:
                    _persist_image(job_id, data_url)
                    image_ready = True
                else:
                    refusal = _assistant_refusal_text(image_page)
                    if refusal and not fallback_sent and not simple._assistant_busy(image_page):
                        fallback_sent = True
                        current_job = additions._row(job_id)
                        official_url = str(current_job.get("source_official_url") or "")
                        if official_url:
                            official_capture = _capture_official_visual(context, job_id, official_url)
                            if official_capture is not None:
                                one_click._emit(
                                    job_id,
                                    "Chat 2 recusou o acesso direto à página oficial; uma captura local acessível foi criada e será anexada ao fallback.",
                                    step="chatgpt_image",
                                    progress=66,
                                )
                                creative._attach_reference(image_page, official_capture, job_id)
                            else:
                                one_click._emit(
                                    job_id,
                                    "Chat 2 recusou o acesso direto à página oficial; seguindo com fallback por pesquisa pública sem exigir abertura da URL.",
                                    step="chatgpt_image",
                                    progress=66,
                                )
                        else:
                            one_click._emit(
                                job_id,
                                "Chat 2 respondeu com recusa textual; reenviando a geração sem exigir acesso direto à página oficial.",
                                step="chatgpt_image",
                                progress=66,
                            )
                        image_before.update(
                            str(item.get("src") or "") for item in capture._image_candidates(image_page)
                        )
                        image_page, _fallback_count, fallback_before = reconnect._send_message_resilient(
                            context,
                            image_page,
                            _fallback_image_prompt(current_job, has_official_capture=official_capture is not None),
                            job_id,
                            project_url,
                        )
                        image_before.update(fallback_before)
                        one_click._emit(
                            job_id,
                            "Fallback do Chat 2 enviado. A geração continua dentro do mesmo limite total de 4 minutos.",
                            step="chatgpt_image",
                            progress=67,
                        )

                    elapsed = now - image_started
                    if elapsed >= _IMAGE_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 2 não entregou uma imagem final válida dentro de 4 minutos, mesmo com o fallback automático quando necessário."
                        )
                    if elapsed >= next_image_log:
                        one_click._emit(
                            job_id,
                            f"Chat 2 ainda processando; nova conferência automática ({int(elapsed)}s/{_IMAGE_TIMEOUT_SECONDS}s).",
                            step="chatgpt_image",
                            progress=68,
                        )
                        next_image_log += _IMAGE_POLL_SECONDS

            time.sleep(0.8)

    return additions._row(job_id)


def install_addition_parallel_generation_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    simple._run_two_chats = _run_parallel_chats
    _INSTALLED = True
