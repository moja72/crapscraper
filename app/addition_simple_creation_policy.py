from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.new_product_workflow_policy as additions
from app.integrations.wordpress import sanitize_text


_INSTALLED = False
_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, "
    "lojas e áreas do site com visual avançado, melhorando apresentação, conversão e flexibilidade "
    "para criar projetos WordPress mais modernos e profissionais. Ele funciona com edição de arrastar "
    "e soltar, widgets premium, templates e construtores para tema, formulários e pop-ups, deixando a "
    "criação mais prática e reduzindo dependência de código no projeto."
)


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def _description_prompt(job: Mapping[str, Any]) -> str:
    kind_label = "tema WordPress" if _kind(job) == "theme" else "plugin WordPress"
    return f"""Escreva SOMENTE a breve descrição comercial deste produto para o e-commerce PluginTema.

Produto: {job.get('source_name') or '-'}
Tipo: {kind_label}
Versão: {job.get('source_version') or '-'}
Página da fonte: {job.get('source_product_url') or '-'}
Página oficial: {job.get('source_official_url') or '-'}

REGRAS OBRIGATÓRIAS
- Responda somente com o texto final da descrição, sem introdução e sem explicações.
- Não escreva título, H1, H2, subtítulos, listas, HTML, Markdown, SEO, meta description, tags ou categoria.
- Não coloque rótulos como "Descrição:" ou "Breve descrição:".
- Use português do Brasil, texto corrido, natural, comercial e informativo.
- Faça aproximadamente 400 a 500 caracteres, em 2 ou 3 frases.
- Comece pelo principal benefício e depois explique de forma fluida o que o produto ajuda a fazer e como ele pode ser usado.
- Não invente recursos que não possam ser inferidos com segurança das informações disponíveis.

Use apenas a estrutura e o tamanho deste exemplo como referência, sem copiar o conteúdo:
"{_DESCRIPTION_EXAMPLE}"

Retorne SOMENTE a descrição final."""


def _clean_description(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:text|markdown)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"^\s*(?:breve\s+descri[cç][aã]o|descri[cç][aã]o)\s*:\s*", "", value, flags=re.I)
    value = " ".join(value.split()).strip().strip('"').strip()
    return value


def _assistant_busy(page: Any) -> bool:
    for selector in (
        "button[data-testid='stop-button']",
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Parar' i]",
        "button[aria-label*='Interromper' i]",
    ):
        try:
            node = page.locator(selector).first
            if node.count() and node.is_visible():
                return True
        except Exception:
            continue
    return False


def _wait_plain_answer(
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

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(
                context, current, job_id, url, timeout_seconds=60
            )

        try:
            messages = one_click._assistant_messages(current)
            count = messages.count()
        except Exception as error:
            if reconnect._is_retryable_browser_error(error):
                current = reconnect._pick_page(context)
                time.sleep(0.8)
                continue
            raise

        if count > before_count:
            try:
                raw = str(messages.nth(count - 1).inner_text() or "").strip()
            except Exception as error:
                if reconnect._is_retryable_browser_error(error):
                    current = reconnect._pick_page(context)
                    time.sleep(0.8)
                    continue
                raw = ""

            cleaned = _clean_description(raw)
            if cleaned and cleaned == last:
                stable += 1
            elif cleaned:
                last = cleaned
                stable = 0

            if len(cleaned) >= 180 and stable >= 2 and not _assistant_busy(current):
                return current, cleaned

        time.sleep(1.1)

    if last:
        return current, last
    raise RuntimeError("Tempo esgotado aguardando a descrição simples do ChatGPT.")


def _fresh_project_chat(context: Any, page: Any, job_id: str, url: str, label: str) -> Any:
    current = page if reconnect._page_is_alive(page) else reconnect._pick_page(context)
    last_error: BaseException | None = None

    for attempt in range(1, 4):
        try:
            one_click._emit(
                job_id,
                f"Abrindo {label} como um novo chat no projeto CS Automação…",
                step="chatgpt",
            )
            current.goto(url, wait_until="domcontentloaded", timeout=60_000)
            composer = one_click._wait_composer(current, job_id, timeout_seconds=120)
            if composer is None:
                raise RuntimeError("A caixa de mensagem do novo chat não apareceu.")
            return current
        except Exception as error:
            last_error = error
            if attempt >= 3 or not reconnect._is_retryable_browser_error(error):
                raise
            current = reconnect._pick_page(context)
            time.sleep(1.0)

    if last_error is not None:
        raise last_error
    return current


def _save_plain_description(job_id: str, description: str) -> dict[str, Any]:
    job = additions._row(job_id)
    title = str(job.get("source_name") or job.get("title") or "Novo produto").strip()
    cleaned = _clean_description(description)
    if len(cleaned) < 180:
        raise RuntimeError("A descrição retornada pelo ChatGPT ficou curta demais para ser usada.")
    additions._update(
        job_id,
        title=title,
        short_description=cleaned,
        description=cleaned,
        seo_title="",
        meta_description="",
        tags="",
        error="",
    )
    additions._recalculate_state(job_id)
    return additions._row(job_id)


def _run_two_chats(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    reference = creative._reference_path(job)
    if not reference.exists():
        raise RuntimeError(
            f"Referência visual obrigatória não encontrada em {reference}. "
            "Confirme Exemplo Plugin.webp e Exemplo Tema.webp em app/static."
        )

    url = coproducao._project_url()
    endpoint, profile_dir = cdp._ensure_debug_browser(url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=8,
    )
    coproducao._wait_login_then_project(job_id, endpoint, url)

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
        page = reconnect._pick_page(context)

        # CHAT 1: somente a descrição curta.
        page = _fresh_project_chat(context, page, job_id, url, "Chat 1/2 — descrição")
        prompt = _description_prompt(job)
        one_click._emit(
            job_id,
            "Chat 1/2: enviando somente o pedido da breve descrição.",
            step="chatgpt_description",
            progress=15,
        )
        page, before_count, _before_images = reconnect._send_message_resilient(
            context, page, prompt, job_id, url
        )
        one_click._emit(
            job_id,
            "Chat 1/2: aguardando somente o texto da descrição…",
            step="chatgpt_description",
            progress=22,
        )
        page, description = _wait_plain_answer(
            context, page, before_count, job_id, url, timeout_seconds=300
        )
        _save_plain_description(job_id, description)
        one_click._emit(
            job_id,
            f"Chat 1/2 concluído: descrição salva ({len(description)} caracteres).",
            step="description_ready",
            progress=40,
        )

        # CHAT 2: volta à raiz do projeto para iniciar outra conversa.
        job = additions._row(job_id)
        page = _fresh_project_chat(context, page, job_id, url, "Chat 2/2 — imagem")
        one_click._emit(
            job_id,
            f"Chat 2/2: anexando a referência {reference.name} antes do prompt.",
            step="chatgpt_image",
            progress=50,
        )
        if not creative._attach_reference(page, reference, job_id):
            raise RuntimeError(
                f"Não foi possível anexar a referência visual obrigatória {reference.name}."
            )

        image_prompt = creative._image_only_prompt(job)
        one_click._emit(
            job_id,
            "Chat 2/2: referência anexada. Enviando somente o pedido da imagem.",
            step="chatgpt_image",
            progress=58,
        )
        page, _count, before_images = reconnect._send_message_resilient(
            context, page, image_prompt, job_id, url
        )
        one_click._emit(
            job_id,
            "Chat 2/2: aguardando a imagem ser gerada…",
            step="chatgpt_image",
            progress=64,
        )
        page, image_source = reconnect._wait_new_image_resilient(
            context,
            page,
            before_images,
            job_id,
            url,
            timeout_seconds=480,
        )
        if not image_source:
            raise RuntimeError("O ChatGPT não retornou uma nova imagem utilizável no Chat 2/2.")

        data_url = one_click._image_data_url(page, image_source)
        image_path = one_click._persist_image(job_id, data_url)
        one_click._emit(
            job_id,
            f"Chat 2/2 concluído: imagem salva em {Path(image_path).name}.",
            step="image_ready",
            progress=78,
        )

    return additions._row(job_id)


def _root_category(woo: Any, kind: str) -> tuple[int, str]:
    wanted = {"plugin", "plugins"} if kind == "plugin" else {"tema", "temas", "theme", "themes"}
    fallback: tuple[int, str] | None = None
    page = 1
    while True:
        batch = list(woo.list_product_categories(page=page, per_page=100) or [])
        for item in batch:
            name = str(item.get("name") or "").strip()
            if _fold(name) not in wanted:
                continue
            candidate = (int(item.get("id") or 0), name)
            if int(item.get("parent") or 0) == 0:
                return candidate
            if fallback is None:
                fallback = candidate
        if len(batch) < 100:
            break
        page += 1
    if fallback:
        return fallback
    label = "Plugin" if kind == "plugin" else "Tema"
    raise RuntimeError(f"Categoria raiz {label} não encontrada no WooCommerce.")


def _create_minimal_product(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    existing_id = int(job.get("woo_product_id") or 0)
    if existing_id:
        one_click._emit(
            job_id,
            f"Produto WooCommerce #{existing_id} já existe; etapa de criação reaproveitada.",
            step="draft_ready",
            progress=96,
        )
        return job

    image_path = Path(str(job.get("image_path") or ""))
    if not image_path.exists():
        raise RuntimeError("A imagem precisa estar pronta antes de criar o produto.")

    description = str(job.get("short_description") or "").strip()
    if not description:
        raise RuntimeError("A descrição precisa estar pronta antes de criar o produto.")

    woo = additions.web._build_store_woocommerce_client()
    title = str(job.get("source_name") or job.get("title") or "Novo produto").strip()
    duplicate = additions._duplicate_product(woo, title)
    if duplicate:
        raise RuntimeError(
            f"Já existe um produto com o mesmo nome no WooCommerce: #{duplicate.get('id')}."
        )

    category_id, category_name = _root_category(woo, _kind(job))

    one_click._emit(
        job_id,
        "Descrição e imagem prontas. Enviando a imagem para a Biblioteca de Mídia…",
        step="image_upload",
        progress=82,
    )
    media_id = int(job.get("media_id") or 0)
    if not media_id:
        media_id = int(additions._wp_media_upload(str(image_path), title) or 0)
    if not media_id:
        raise RuntimeError("O WordPress não confirmou o upload da imagem gerada.")

    payload = {
        "name": title,
        "type": "simple",
        "status": "draft",
        "description": description,
        "short_description": description,
        "categories": [{"id": category_id}],
        "images": [{"id": media_id}],
        "meta_data": [
            {"key": "crapscraper_addition_job", "value": job_id},
        ],
    }

    one_click._emit(
        job_id,
        f"Criando novo item somente na categoria raiz {category_name}…",
        step="draft",
        progress=90,
    )
    product = additions._wc_request(woo, "POST", "/wp-json/wc/v3/products", payload)
    product_id = int(product.get("id") or 0)
    if not product_id:
        raise RuntimeError("WooCommerce não retornou o ID do novo produto.")

    fresh = woo.get_product_fresh(product_id)
    category_ids = {
        int(item.get("id") or 0)
        for item in (fresh.get("categories") or [])
        if isinstance(item, Mapping)
    }
    if category_id not in category_ids:
        raise RuntimeError("WooCommerce criou o produto, mas não confirmou a categoria raiz esperada.")

    job = additions._update(
        job_id,
        state="draft_created",
        woo_product_id=product_id,
        media_id=media_id,
        error="",
    )
    one_click._emit(
        job_id,
        f"Produto WooCommerce #{product_id} criado como rascunho na categoria {category_name}.",
        step="draft_ready",
        progress=100,
    )
    return job


def _run_simple(job_id: str, manager: Any) -> None:
    del manager  # Este fluxo provisório não baixa ZIP nem prepara preços.
    with one_click._TASK_LOCK:
        task = one_click._task(job_id)
        task.update(
            running=True,
            done=False,
            error="",
            step="starting",
            progress=1,
            logs=[],
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            finished_at="",
        )

    try:
        additions._row(job_id)
        one_click._emit(
            job_id,
            "Iniciando fluxo simplificado: Chat 1 descrição → Chat 2 imagem → produto na loja.",
            step="starting",
            progress=2,
        )
        _run_two_chats(job_id)
        _create_minimal_product(job_id)

        one_click._emit(
            job_id,
            "Fluxo concluído. Produto criado como rascunho somente na categoria raiz Plugin/Tema.",
            step="completed",
            progress=100,
        )
        with one_click._TASK_LOCK:
            task = one_click._task(job_id)
            task["running"] = False
            task["done"] = True
            task["error"] = ""
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception as error:
        message = sanitize_text(error)
        try:
            additions._update(job_id, error=message)
        except Exception:
            pass
        one_click._emit(job_id, f"ERRO: {message}", step="error")
        with one_click._TASK_LOCK:
            task = one_click._task(job_id)
            task["running"] = False
            task["done"] = False
            task["error"] = message
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def install_addition_simple_creation_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    one_click._run = _run_simple
    _INSTALLED = True
