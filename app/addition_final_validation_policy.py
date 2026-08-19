from __future__ import annotations

import base64
import hashlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_response_reader_policy as response_reader
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions
from app.integrations.wordpress import sanitize_text


_INSTALLED = False
_ORIGINAL_PLAUSIBLE = None
_ORIGINAL_RESET_JOB = None

_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, lojas e áreas "
    "do site com visual avançado, melhorando apresentação, conversão e flexibilidade para criar projetos WordPress "
    "mais modernos e profissionais. Ele funciona com edição de arrastar e soltar, widgets premium, templates e "
    "construtores para tema, formulários e pop-ups, deixando a criação mais prática e reduzindo dependência de código no projeto."
)

_CODE_MARKERS = (
    "function ",
    "=>",
    "addeventlistener",
    "requestanimationframe",
    "performance.mark",
    "document.currentscript",
    "window.oai_",
    "window.oai",
    "composer.first-prompt-input",
    "javascript:",
    "<script",
    "</script",
    "document.queryselector",
    "document.queryselectorall",
    "window.__",
)

_USER_PROMPT_MARKERS = (
    "gere apenas a breve descrição comercial deste produto",
    "escreva somente a breve descrição comercial deste produto",
    "retorne somente o parágrafo final da breve descrição",
)

_IMAGE_ERROR_MARKERS = (
    "algo deu errado. tente novamente",
    "something went wrong. try again",
    "there was an error generating",
    "erro ao gerar",
)


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _description_prompt(job: Mapping[str, Any]) -> str:
    kind_label = "tema WordPress" if _kind(job) == "theme" else "plugin WordPress"
    source_url = str(job.get("source_product_url") or "").strip()
    official_url = str(job.get("source_official_url") or "").strip()
    return f"""Gere apenas a breve descrição comercial deste produto para o e-commerce PluginTema.

PRODUTO
Nome: {job.get('source_name') or '-'}
Tipo: {kind_label}
Versão de referência: {job.get('source_version') or '-'}
Página da fonte: {source_url or '-'}
Página oficial: {official_url or '-'}

FONTE PRINCIPAL DE CONTEXTO
Antes de escrever, consulte e analise as páginas fornecidas acima quando estiverem acessíveis. Use o conteúdo real dessas páginas como fonte principal para entender a marca/produto, finalidade, nicho, recursos descritos, público e linguagem visual. O nome do produto sozinho é apenas contexto complementar. Não copie a descrição da fonte; produza um texto original.

OBJETIVO
Escreva UM ÚNICO PARÁGRAFO em português do Brasil, com aproximadamente 400 a 500 caracteres e 2 ou 3 frases. O resultado deve parecer uma breve descrição real de e-commerce WordPress: comercial, específica, fluida e informativa.

ESTRUTURA DESEJADA
1. Comece com uma frase curta centrada no principal benefício ou uso do produto.
2. Mencione o nome do produto naturalmente e explique o que ele ajuda a criar, organizar, melhorar ou executar com base na página consultada.
3. Conclua indicando para que tipo de projeto ou usuário ele é útil, sem repetir a mesma ideia.

QUALIDADE
- Priorize fatos que estejam visíveis ou claramente sustentados nas páginas fornecidas.
- Não invente recursos, integrações, compatibilidades, números, marcas ou benefícios não confirmados.
- Não inclua a versão no texto final.
- Evite clichês vazios como "uma opção versátil", "solução completa", "presença online" e "leve seu projeto para outro nível" quando não acrescentarem informação.
- Não use título, subtítulo, H1, H2, listas, HTML, Markdown, SEO, meta description, tags, categoria, observações ou explicações.
- Não escreva rótulos como "Descrição:" ou "Breve descrição:".

Use somente a estrutura, ritmo e extensão deste exemplo como referência; não copie o conteúdo:
"{_DESCRIPTION_EXAMPLE}"

Retorne SOMENTE o parágrafo final da breve descrição."""


def _image_prompt(job: Mapping[str, Any]) -> str:
    title = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    source_url = str(job.get("source_product_url") or "").strip()
    official_url = str(job.get("source_official_url") or "").strip()
    kind = _kind(job)

    source_block = (
        f"Produto: {title}\n"
        f"Tipo: {'tema WordPress' if kind == 'theme' else 'plugin WordPress'}\n"
        f"Página da fonte: {source_url or '-'}\n"
        f"Página oficial: {official_url or '-'}"
    )

    if kind == "theme":
        visual = """TEMA — COMPOSIÇÃO OBRIGATÓRIA
- Use o arquivo anexado 'exemplo tema.webp' SOMENTE como referência de composição, proporção, mockup e acabamento. NÃO copie a marca, as telas, textos, cores ou conteúdo visual da referência.
- Mostre um monitor Apple e um celular, ambos inteiros e claramente visíveis. A posição do celular pode variar.
- Nas duas telas, represente o tema REAL do produto atual. Use screenshots, identidade visual, cores, logo/nome e estilo que possam ser identificados nas páginas fornecidas.
- A imagem deve deixar claro que as telas pertencem ao produto atual, e não ao exemplo anexado."""
    else:
        visual = """PLUGIN — COMPOSIÇÃO OBRIGATÓRIA
- Use o arquivo anexado 'exemplo plugin.webp' SOMENTE como referência de composição, proporção da caixa 3D e acabamento. NÃO copie a marca, textos, cores ou conteúdo visual da referência.
- Crie uma caixa profissional mostrando pelo menos 3 faces/lados visíveis; o ângulo pode variar.
- Use a identidade REAL do plugin atual: nome, cores e, se estiver claramente identificável nas páginas fornecidas, o logotipo real. Não invente um logotipo caso ele não possa ser confirmado.
- Use fonte Quicksand nas informações da embalagem e deixe visível exatamente: "Vitalício | Ilimitado | Atualizado"."""

    return f"""Agora gere SOMENTE a imagem principal deste produto. Não responda com texto fora da geração da imagem.

{source_block}

PESQUISA VISUAL OBRIGATÓRIA
Antes de gerar, consulte e analise as páginas da fonte/oficial fornecidas. Elas são a referência principal para identificar a marca, o nome, as cores, o logo quando disponível, screenshots e a aparência real do produto. O arquivo anexado serve apenas como MODELO DE MOCKUP/COMPOSIÇÃO.

{visual}

REQUISITOS FINAIS
- Imagem quadrada 1:1.
- Fundo totalmente transparente, inclusive nas bordas e áreas vazias.
- Alta qualidade e acabamento profissional para capa de produto em e-commerce.
- Não use cenário ou fundo sólido.
- Não corte os dispositivos ou a caixa.
- Não reutilize a imagem anexada como resultado final.
- Não invente identidade visual diferente da encontrada nas páginas do produto.
- Gere uma NOVA imagem final baseada no produto atual e aguarde a geração terminar completamente."""


def _looks_like_code_or_prompt(text: str) -> bool:
    lowered = str(text or "").lower()
    if any(marker in lowered for marker in _CODE_MARKERS):
        return True
    if any(marker in lowered for marker in _USER_PROMPT_MARKERS):
        return True
    if lowered.count("{") + lowered.count("}") >= 4:
        return True
    return False


def _validated_description(text: str) -> str:
    cleaned = simple._clean_description(text)
    if not cleaned:
        return ""
    if len(cleaned) < 260 or len(cleaned) > 750:
        return ""
    if _looks_like_code_or_prompt(cleaned):
        return ""
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", cleaned))
    if sentence_count < 2:
        return ""
    letters = sum(1 for char in cleaned if char.isalpha())
    if letters < max(120, int(len(cleaned) * 0.55)):
        return ""
    return cleaned


def _plausible_description(text: str) -> str:
    base = str(text or "")
    if _ORIGINAL_PLAUSIBLE is not None:
        try:
            base = _ORIGINAL_PLAUSIBLE(text)
        except Exception:
            base = str(text or "")
    return _validated_description(base)


def _save_plain_description(job_id: str, description: str) -> dict[str, Any]:
    cleaned = _validated_description(description)
    if not cleaned:
        raise RuntimeError(
            "A resposta localizada no ChatGPT não passou na validação de descrição comercial. "
            "Código da interface, prompts e textos técnicos são rejeitados automaticamente."
        )
    job = additions._row(job_id)
    title = str(job.get("source_name") or job.get("title") or "Novo produto").strip()
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


def _image_candidates(page: Any) -> list[dict[str, str]]:
    try:
        result = page.evaluate(
            """
            () => [...document.images]
              .filter(img => img.naturalWidth >= 256 && img.naturalHeight >= 256)
              .map(img => {
                const turn = img.closest('[data-testid*="conversation-turn"], article');
                const roleNode =
                  img.closest('[data-message-author-role]') ||
                  (turn && (turn.matches('[data-message-author-role]') ? turn : turn.querySelector('[data-message-author-role]')));
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                const text = String(turn?.innerText || '').trim();
                return {
                  src: String(img.currentSrc || img.src || ''),
                  role,
                  text,
                  testid: String(turn?.getAttribute('data-testid') || '')
                };
              })
              .filter(item => item.src && !item.src.includes('avatar') && !item.src.includes('icon'))
            """
        )
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for item in result or []:
        if isinstance(item, Mapping):
            rows.append({
                "src": str(item.get("src") or ""),
                "role": str(item.get("role") or "").lower(),
                "text": str(item.get("text") or ""),
                "testid": str(item.get("testid") or ""),
            })
    return rows


def _candidate_score(item: Mapping[str, str]) -> int:
    role = str(item.get("role") or "").lower()
    text = str(item.get("text") or "").lower()
    if role == "user":
        return -1000
    if "agora gere somente a imagem principal" in text or "pesquisa visual obrigatória" in text:
        return -1000
    if role == "assistant":
        return 100
    if "worked for" in text or "edit" in text or "editar" in text:
        return 60
    return 10


def _decode_data_url(data_url: str) -> bytes:
    match = re.match(r"^data:image/[^;]+;base64,(.+)$", str(data_url or ""), re.I | re.S)
    if not match:
        return b""
    try:
        return base64.b64decode(match.group(1), validate=False)
    except Exception:
        return b""


def _reference_hash(job_id: str) -> tuple[Path, str]:
    job = additions._row(job_id)
    reference = creative._reference_path(job)
    if not reference.exists():
        return reference, ""
    return reference, hashlib.sha256(reference.read_bytes()).hexdigest()


def _is_generation_error_visible(page: Any) -> bool:
    try:
        text = str(page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        return False
    return any(marker in text for marker in _IMAGE_ERROR_MARKERS)


def _click_retry(page: Any) -> bool:
    selectors = (
        "button:has-text('Repetir')",
        "button:has-text('Retry')",
        "button:has-text('Tentar novamente')",
        "button[aria-label*='Retry' i]",
        "button[aria-label*='Repetir' i]",
    )
    for selector in selectors:
        try:
            button = page.locator(selector).last
            if button.count() and button.is_visible() and button.is_enabled():
                button.click()
                return True
        except Exception:
            continue
    return False


def _wait_generated_image(
    context: Any,
    page: Any,
    before: set[str],
    job_id: str,
    url: str,
    *,
    timeout_seconds: int,
) -> tuple[Any, str]:
    deadline = time.time() + timeout_seconds
    started = time.time()
    current = page
    stable_source = ""
    stable_count = 0
    retry_used = False
    rejected_reference_logged = False
    reference, reference_sha = _reference_hash(job_id)

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(
                context, current, job_id, url, timeout_seconds=60
            )

        elapsed = time.time() - started
        busy = simple._assistant_busy(current)
        candidates = [
            item for item in _image_candidates(current)
            if item.get("src") not in before and _candidate_score(item) >= 0
        ]
        candidates.sort(key=_candidate_score)
        candidate = candidates[-1] if candidates else None

        if candidate and elapsed >= 8:
            source = str(candidate.get("src") or "")
            if source == stable_source:
                stable_count += 1
            else:
                stable_source = source
                stable_count = 0

            if stable_count >= 1 and not busy:
                try:
                    data_url = one_click._image_data_url(current, source)
                    raw = _decode_data_url(data_url)
                except Exception:
                    raw = b""
                candidate_sha = hashlib.sha256(raw).hexdigest() if raw else ""
                if candidate_sha and reference_sha and candidate_sha == reference_sha:
                    if not rejected_reference_logged:
                        one_click._emit(
                            job_id,
                            f"A miniatura de {reference.name} apareceu entre as imagens, mas foi ignorada por ser a referência e não o resultado final.",
                            step="chatgpt_image",
                            progress=66,
                        )
                        rejected_reference_logged = True
                    stable_source = ""
                    stable_count = 0
                elif len(raw) >= 15_000:
                    return current, source

        if (
            not retry_used
            and elapsed >= 20
            and not busy
            and _is_generation_error_visible(current)
            and _click_retry(current)
        ):
            retry_used = True
            before.update(item.get("src", "") for item in _image_candidates(current))
            one_click._emit(
                job_id,
                "O ChatGPT exibiu erro de geração; o botão Repetir foi acionado automaticamente e o fluxo continua aguardando a nova imagem.",
                step="chatgpt_image",
                progress=65,
            )
            started = time.time()
            stable_source = ""
            stable_count = 0

        time.sleep(1.3)

    return current, ""


def _validate_image_file(job_id: str, image_path: Path) -> None:
    if not image_path.exists() or not image_path.is_file():
        raise RuntimeError("A imagem final não existe no disco.")
    raw = image_path.read_bytes()
    if len(raw) < 15_000:
        raise RuntimeError("A imagem final parece pequena ou incompleta demais para publicação.")
    reference, reference_sha = _reference_hash(job_id)
    current_sha = hashlib.sha256(raw).hexdigest()
    if reference_sha and current_sha == reference_sha:
        raise RuntimeError(
            f"A imagem capturada é exatamente a referência {reference.name}, não uma nova geração do produto."
        )


def _remote_product_missing(error: BaseException) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in ("404", "not found", "não encontrado", "nao encontrado"))


def _create_validate_publish(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    description = _validated_description(str(job.get("short_description") or ""))
    if not description:
        raise RuntimeError("A descrição salva não passou na validação final; o produto não será enviado à loja.")

    image_path = Path(str(job.get("image_path") or ""))
    _validate_image_file(job_id, image_path)

    woo = additions.web._build_store_woocommerce_client()
    title = str(job.get("source_name") or job.get("title") or "Novo produto").strip()
    category_id, category_name = simple._root_category(woo, _kind(job))
    existing_id = int(job.get("woo_product_id") or 0)

    existing_product: Mapping[str, Any] | None = None
    if existing_id:
        try:
            existing_product = woo.get_product_fresh(existing_id)
        except Exception as error:
            if not _remote_product_missing(error):
                raise
            additions._update(job_id, woo_product_id=0, media_id=0, state="content_ready", error="")
            existing_id = 0
            existing_product = None
            one_click._emit(
                job_id,
                "O rascunho anterior não existe mais no WooCommerce; o vínculo local foi limpo e o cadastro será recriado.",
                step="store_validation",
                progress=80,
            )

    if not existing_id:
        duplicate = additions._duplicate_product(woo, title)
        if duplicate:
            raise RuntimeError(
                f"Já existe um produto com o mesmo nome no WooCommerce: #{duplicate.get('id')}. "
                "Exclua ou revise esse item antes de tentar novamente."
            )

    one_click._emit(
        job_id,
        "Descrição e imagem passaram na validação local. Enviando a imagem final para a Biblioteca de Mídia…",
        step="image_upload",
        progress=82,
    )
    media_id = int(additions._wp_media_upload(str(image_path), title) or 0)
    if not media_id:
        raise RuntimeError("O WordPress não confirmou o upload da imagem final validada.")

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
            {"key": "crapscraper_source_url", "value": str(job.get("source_product_url") or "")},
        ],
    }

    if existing_id:
        one_click._emit(
            job_id,
            f"Atualizando o rascunho WooCommerce #{existing_id} com o conteúdo validado…",
            step="draft",
            progress=88,
        )
        additions._wc_request(woo, "PUT", f"/wp-json/wc/v3/products/{existing_id}", payload)
        product_id = existing_id
    else:
        one_click._emit(
            job_id,
            f"Criando rascunho temporário somente na categoria raiz {category_name}…",
            step="draft",
            progress=88,
        )
        product = additions._wc_request(woo, "POST", "/wp-json/wc/v3/products", payload)
        product_id = int(product.get("id") or 0)
        if not product_id:
            raise RuntimeError("WooCommerce não retornou o ID do rascunho temporário.")

    draft = woo.get_product_fresh(product_id)
    draft_categories = {
        int(item.get("id") or 0)
        for item in (draft.get("categories") or [])
        if isinstance(item, Mapping)
    }
    draft_images = {
        int(item.get("id") or 0)
        for item in (draft.get("images") or [])
        if isinstance(item, Mapping)
    }
    if str(draft.get("status") or "") != "draft":
        raise RuntimeError("O WooCommerce não confirmou o estado de rascunho antes da publicação.")
    if category_id not in draft_categories:
        raise RuntimeError("O rascunho não confirmou a categoria raiz esperada.")
    if media_id not in draft_images:
        raise RuntimeError("O rascunho não confirmou a imagem final validada.")
    if not _validated_description(str(draft.get("short_description") or "")):
        raise RuntimeError("O rascunho não confirmou a descrição validada.")

    additions._update(
        job_id,
        state="draft_created",
        woo_product_id=product_id,
        media_id=media_id,
        error="",
    )
    one_click._emit(
        job_id,
        f"Rascunho WooCommerce #{product_id} validado. Publicando somente agora…",
        step="publishing",
        progress=95,
    )

    additions._wc_request(woo, "PUT", f"/wp-json/wc/v3/products/{product_id}", {"status": "publish"})
    published = woo.get_product_fresh(product_id)
    published_categories = {
        int(item.get("id") or 0)
        for item in (published.get("categories") or [])
        if isinstance(item, Mapping)
    }
    published_images = {
        int(item.get("id") or 0)
        for item in (published.get("images") or [])
        if isinstance(item, Mapping)
    }
    if str(published.get("status") or "") != "publish":
        raise RuntimeError("O WooCommerce não confirmou a publicação final.")
    if category_id not in published_categories or media_id not in published_images:
        raise RuntimeError("O produto foi publicado, mas a validação final de categoria/imagem falhou.")
    if not _validated_description(str(published.get("short_description") or "")):
        raise RuntimeError("O produto foi publicado, mas a descrição final não passou na releitura.")

    job = additions._update(
        job_id,
        state="completed",
        woo_product_id=product_id,
        media_id=media_id,
        completed_at=additions._utc_now(),
        error="",
    )
    one_click._emit(
        job_id,
        f"Produto WooCommerce #{product_id} publicado e validado com descrição, imagem e categoria {category_name}.",
        step="completed",
        progress=100,
    )
    return job


def _run_final(job_id: str, manager: Any) -> None:
    del manager
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
        job = additions._row(job_id)
        if str(job.get("state") or "") == "completed" and int(job.get("woo_product_id") or 0):
            one_click._emit(job_id, "Este produto já foi publicado e concluído.", step="completed", progress=100)
        else:
            one_click._emit(
                job_id,
                "Iniciando fluxo validado: Chat 1 descrição → Chat 2 imagem → rascunho temporário → publicação.",
                step="starting",
                progress=2,
            )
            simple._run_two_chats(job_id)
            _create_validate_publish(job_id)

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


def _reset_deleted_remote_job(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if product_id:
        woo = additions.web._build_store_woocommerce_client()
        try:
            product = woo.get_product_fresh(product_id)
        except Exception as error:
            if not _remote_product_missing(error):
                raise ValueError(
                    "Não foi possível confirmar se o produto remoto ainda existe; o reset foi bloqueado por segurança."
                ) from None
        else:
            if isinstance(product, Mapping) and int(product.get("id") or 0):
                raise ValueError(
                    f"O produto WooCommerce #{product_id} ainda existe. Exclua-o primeiro e execute o reset novamente."
                )

    image_path = Path(str(job.get("image_path") or ""))
    try:
        if image_path.exists() and image_path.is_file():
            image_path.unlink()
    except OSError:
        pass

    with additions._db() as connection:
        connection.execute("DELETE FROM addition_jobs WHERE job_id=?", (job_id,))
    additions._sync_approved()
    with one_click._TASK_LOCK:
        one_click._TASKS.pop(job_id, None)
    return {
        "ok": True,
        "message": "Job local resetado e reconstruído a partir da aprovação. O item pode ser adicionado novamente.",
    }


def install_addition_final_validation_policy() -> None:
    global _INSTALLED, _ORIGINAL_PLAUSIBLE, _ORIGINAL_RESET_JOB
    if _INSTALLED:
        return

    _ORIGINAL_PLAUSIBLE = response_reader._plausible_description
    _ORIGINAL_RESET_JOB = additions._reset_job

    response_reader._plausible_description = _plausible_description
    simple._description_prompt = _description_prompt
    simple._save_plain_description = _save_plain_description
    creative._image_only_prompt = _image_prompt
    reconnect._wait_new_image_resilient = _wait_generated_image
    simple._create_minimal_product = _create_validate_publish
    additions._reset_job = _reset_deleted_remote_job
    one_click._run = _run_final

    _INSTALLED = True
