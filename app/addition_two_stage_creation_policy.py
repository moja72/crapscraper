from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from app import settings
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.chatgpt_browser_assist as chatgpt
import app.new_product_workflow_policy as additions
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_RUN: Callable[[str, Any], None] | None = None


def _job_kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _price_defaults_for_kind(kind: str) -> tuple[dict[str, str], dict[str, Any] | None]:
    from app.store_pricing import read_store_price_reference_products, variation_period

    resolved_kind = "theme" if str(kind or "").strip().lower() == "theme" else "plugin"
    woo = additions.web._build_store_woocommerce_client()
    refs = read_store_price_reference_products(
        Path(settings.COMPARISON_IMPORTS_DIR),
        (resolved_kind,),
        limit_per_kind=1,
    )
    if not refs:
        return {}, None

    reference = dict(refs[0])
    product_id = int(reference.get("id") or 0)
    if not product_id:
        return {}, reference

    defaults = {
        "annual_regular": "",
        "annual_sale": "",
        "lifetime_regular": "",
        "lifetime_sale": "",
    }
    for variation in list(woo.list_variations(product_id, per_page=100) or []):
        period = variation_period(variation)
        if period not in {"annual", "lifetime"}:
            continue
        defaults[f"{period}_regular"] = str(variation.get("regular_price", "") or "").strip()
        defaults[f"{period}_sale"] = str(variation.get("sale_price", "") or "").strip()

    return defaults, reference


def _ensure_default_prices(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    required = ("annual_regular", "lifetime_regular")
    if all(str(job.get(field) or "").strip() for field in required):
        return job

    defaults, reference = _price_defaults_for_kind(_job_kind(job))
    if not defaults.get("annual_regular") or not defaults.get("lifetime_regular"):
        label = "tema" if _job_kind(job) == "theme" else "plugin"
        raise RuntimeError(
            f"Não foi possível localizar os preços padrão de {label} no catálogo PluginTema. "
            "Atualize o catálogo/preços da Loja antes de tentar novamente."
        )

    updates: dict[str, str] = {}
    for field in ("annual_regular", "annual_sale", "lifetime_regular", "lifetime_sale"):
        if not str(job.get(field) or "").strip() and field in defaults:
            updates[field] = str(defaults.get(field) or "").strip()

    if updates:
        job = additions._update(job_id, **updates)
        ref_name = str((reference or {}).get("name") or "").strip()
        ref_id = int((reference or {}).get("id") or 0)
        source = f"#{ref_id}" + (f" {ref_name}" if ref_name else "") if ref_id else "produto de referência"
        one_click._emit(
            job_id,
            f"Preços padrão de {_job_kind(job)} aplicados a partir de {source}.",
            step="pricing",
            progress=35,
        )
    return job


def _project_context(job_id: str, *, progress: int, action: str) -> tuple[str, str]:
    url = coproducao._project_url()
    endpoint, profile_dir = cdp._ensure_debug_browser(url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP para {action}. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=progress,
    )
    coproducao._wait_login_then_project(job_id, endpoint, url)
    return url, endpoint


def _run_text_automation(job_id: str) -> None:
    job = additions._row(job_id)
    if additions._content_complete(job):
        one_click._emit(
            job_id,
            "Conteúdo textual já está pronto; etapa de descrição reaproveitada.",
            step="chatgpt_content",
            progress=30,
        )
        return

    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Não foi possível montar o prompt textual do produto.")

    one_click._emit(
        job_id,
        "Etapa 1/2: abrindo o ChatGPT para gerar somente descrição, SEO, tags e categoria…",
        step="chatgpt_content",
        progress=8,
    )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

    url, endpoint = _project_context(
        job_id,
        progress=10,
        action="gerar o conteúdo textual",
    )

    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
                contexts = list(browser.contexts)
                if not contexts:
                    raise RuntimeError("Chrome autenticado, mas nenhum contexto de navegação foi encontrado.")
                context = contexts[0]
                page = reconnect._pick_page(context)
                page = reconnect._ensure_project_page_resilient(
                    context,
                    page,
                    job_id,
                    url,
                    timeout_seconds=120,
                )
                one_click._emit(
                    job_id,
                    "Prompt 1/2 enviado: somente conteúdo editorial.",
                    step="chatgpt_content",
                    progress=16,
                )
                page, before_count, _before_images = reconnect._send_message_resilient(
                    context,
                    page,
                    prompt,
                    job_id,
                    url,
                )
                one_click._emit(
                    job_id,
                    "Aguardando descrição, SEO, tags e categoria…",
                    step="chatgpt_content",
                    progress=20,
                )
                page, answer = reconnect._wait_complete_answer_resilient(
                    context,
                    page,
                    before_count,
                    job_id,
                    url,
                    timeout_seconds=420,
                )
                one_click._save_text(job_id, answer)
                one_click._emit(
                    job_id,
                    "Conteúdo textual recebido e salvo. O produto já pode avançar para a loja.",
                    step="content_ready",
                    progress=30,
                )
                return
        except Exception as error:
            last_error = error
            if attempt >= 3 or not reconnect._is_retryable_browser_error(error):
                raise
            one_click._emit(
                job_id,
                f"O alvo do Chrome mudou durante o conteúdo. Reconectando ({attempt + 1}/3)…",
                step="chatgpt_reconnect",
                progress=12,
            )
            time.sleep(1.2)

    if last_error is not None:
        raise last_error


def _assisted_text_fallback(job_id: str) -> None:
    job = additions._row(job_id)
    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    one_click._emit(
        job_id,
        "Automação textual direta indisponível. Abrindo o modo assistido somente para o conteúdo.",
        step="chatgpt_assisted",
        progress=10,
    )
    chatgpt.open_for_job(job_id)
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        clipboard = one_click._read_clipboard()
        if clipboard and clipboard != prompt:
            try:
                chatgpt.import_text(job_id, clipboard)
                one_click._emit(
                    job_id,
                    "Resposta textual copiada detectada e importada.",
                    step="content_ready",
                    progress=30,
                )
                return
            except Exception:
                pass
        time.sleep(2)
    raise RuntimeError("Tempo esgotado aguardando o conteúdo no modo assistido do ChatGPT.")


def _ensure_text_content(job_id: str) -> None:
    if additions._content_complete(additions._row(job_id)):
        return
    try:
        _run_text_automation(job_id)
    except Exception as automatic_error:
        one_click._emit(
            job_id,
            f"Automação textual do ChatGPT não concluiu: {sanitize_text(automatic_error)}",
            step="chatgpt_content",
        )
        _assisted_text_fallback(job_id)


def _ensure_zip(job_id: str, manager: Any) -> dict[str, Any]:
    job = additions._row(job_id)
    zip_ready = bool(
        str(job.get("zip_path") or "").strip()
        and Path(str(job.get("zip_path"))).exists()
    )
    if zip_ready:
        one_click._emit(
            job_id,
            "ZIP já preparado; reaproveitando arquivo existente.",
            step="zip_ready",
            progress=50,
        )
        return job

    one_click._emit(
        job_id,
        "Preparando ZIP enquanto o cadastro avança para a loja…",
        step="zip",
        progress=38,
    )
    additions._download_source(job_id, manager)
    one_click._emit(
        job_id,
        "ZIP preparado e validado.",
        step="zip_ready",
        progress=50,
    )
    return additions._row(job_id)


def _create_draft_without_image(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    if int(job.get("woo_product_id") or 0):
        one_click._emit(
            job_id,
            f"Rascunho WooCommerce #{int(job.get('woo_product_id') or 0)} já existe; reaproveitando.",
            step="draft_ready",
            progress=68,
        )
        return job

    base_create = cdp._ORIGINAL_CREATE_DRAFT
    if not callable(base_create):
        raise RuntimeError("Fluxo base de criação do rascunho não está disponível.")

    one_click._emit(
        job_id,
        "Criando o produto na loja agora, antes da geração da imagem…",
        step="draft",
        progress=55,
    )
    result = base_create(job_id, "CRIAR RASCUNHO")
    job = dict(result.get("job") or additions._row(job_id))
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("WooCommerce não confirmou o ID do rascunho.")
    one_click._emit(
        job_id,
        f"Rascunho WooCommerce #{product_id} criado com conteúdo, categoria, tags, preços e ZIP.",
        step="draft_ready",
        progress=68,
    )
    return job


def _apply_image_to_product(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("O produto precisa existir no WooCommerce antes de aplicar a imagem.")

    image_path = Path(str(job.get("image_path") or ""))
    if not image_path.exists():
        raise RuntimeError("Imagem gerada não foi encontrada no disco.")

    media_id = int(job.get("media_id") or 0)
    if not media_id:
        one_click._emit(
            job_id,
            "Enviando a imagem final para a Biblioteca de Mídia do WordPress…",
            step="image_upload",
            progress=88,
        )
        media_id = int(
            additions._wp_media_upload(
                str(image_path),
                str(job.get("title") or job.get("source_name") or "Produto"),
            )
            or 0
        )
        if not media_id:
            raise RuntimeError(
                "A imagem foi gerada, mas o WordPress não confirmou o upload para a Biblioteca de Mídia."
            )

    woo = additions.web._build_store_woocommerce_client()
    additions._wc_request(
        woo,
        "PUT",
        f"/wp-json/wc/v3/products/{product_id}",
        {"images": [{"id": media_id}]},
    )
    product = woo.get_product_fresh(product_id)
    image_ids = {
        int(item.get("id") or 0)
        for item in (product.get("images") or [])
        if isinstance(item, Mapping)
    }
    if media_id not in image_ids:
        raise RuntimeError("WooCommerce não confirmou a imagem principal no rascunho.")

    job = additions._update(job_id, media_id=media_id, error="")
    one_click._emit(
        job_id,
        f"Imagem principal aplicada ao WooCommerce #{product_id}.",
        step="image_ready",
        progress=91,
    )
    return job


def _prepare_image_request(page: Any, job: Mapping[str, Any], job_id: str) -> tuple[Path, bool, str]:
    """Usa a referência local quando possível e monta fallback visual quando não for possível."""
    reference = creative._reference_path(job)
    reference_attached = creative._attach_reference(page, reference, job_id)
    image_prompt = creative._image_only_prompt(job, reference_attached=reference_attached)
    return reference, reference_attached, image_prompt


def _run_image_automation(job_id: str) -> None:
    job = additions._row(job_id)
    image_path = Path(str(job.get("image_path") or ""))
    if image_path.exists():
        one_click._emit(
            job_id,
            "Imagem já gerada; reaproveitando arquivo local.",
            step="image_ready",
            progress=84,
        )
        _apply_image_to_product(job_id)
        return

    one_click._emit(
        job_id,
        "Etapa 2/2: gerando imagem do produto; o mockup local será usado somente se estiver disponível.",
        step="chatgpt_image",
        progress=72,
    )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para gerar a imagem: {type(error).__name__}"
        ) from None

    url, endpoint = _project_context(
        job_id,
        progress=74,
        action="gerar a imagem",
    )

    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
                contexts = list(browser.contexts)
                if not contexts:
                    raise RuntimeError("Chrome autenticado, mas nenhum contexto de navegação foi encontrado.")
                context = contexts[0]
                page = reconnect._pick_page(context)
                page = reconnect._ensure_project_page_resilient(
                    context,
                    page,
                    job_id,
                    url,
                    timeout_seconds=120,
                )

                reference, reference_attached, image_prompt = _prepare_image_request(page, job, job_id)
                one_click._emit(
                    job_id,
                    (
                        f"Prompt 2/2: referência {reference.name} anexada; enviando somente as instruções da imagem."
                        if reference_attached
                        else "Prompt 2/2: sem referência local anexada; usando a composição visual definida para o produto."
                    ),
                    step="chatgpt_image",
                    progress=78,
                )
                page, _count, before_images = reconnect._send_message_resilient(
                    context,
                    page,
                    image_prompt,
                    job_id,
                    url,
                )
                page, image_source = reconnect._wait_new_image_resilient(
                    context,
                    page,
                    before_images,
                    job_id,
                    url,
                    timeout_seconds=420,
                )
                if not image_source:
                    raise RuntimeError("O ChatGPT não retornou uma nova imagem utilizável.")

                data_url = one_click._image_data_url(page, image_source)
                image_path_text = one_click._persist_image(job_id, data_url)
                one_click._emit(
                    job_id,
                    f"Imagem gerada e salva localmente: {Path(image_path_text).name}.",
                    step="image_ready",
                    progress=85,
                )
                _apply_image_to_product(job_id)
                return
        except Exception as error:
            last_error = error
            if attempt >= 3 or not reconnect._is_retryable_browser_error(error):
                raise
            one_click._emit(
                job_id,
                f"O alvo do Chrome mudou durante a imagem. Reconectando ({attempt + 1}/3)…",
                step="chatgpt_reconnect",
                progress=76,
            )
            time.sleep(1.2)

    if last_error is not None:
        raise last_error


def _publish_product(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    if str(job.get("state") or "") in {"published", "completed"}:
        return job

    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("Rascunho WooCommerce não disponível para publicação.")

    one_click._emit(
        job_id,
        f"Publicando WooCommerce #{product_id} após validar a imagem final…",
        step="publish",
        progress=95,
    )
    result = additions._publish(job_id, f"PUBLICAR {product_id}")
    return dict(result.get("job") or additions._row(job_id))


def _run_two_stage(job_id: str, manager: Any) -> None:
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
            "Iniciando cadastro em duas etapas: conteúdo → loja → imagem → publicação.",
            step="starting",
            progress=2,
        )

        _ensure_text_content(job_id)
        _ensure_default_prices(job_id)
        _ensure_zip(job_id, manager)
        _create_draft_without_image(job_id)
        _run_image_automation(job_id)
        _publish_product(job_id)

        one_click._emit(
            job_id,
            "Produto adicionado, imagem aplicada e publicação validada com sucesso.",
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


def install_addition_two_stage_creation_policy() -> None:
    global _INSTALLED, _BASE_RUN
    if _INSTALLED:
        return

    _BASE_RUN = one_click._run
    one_click._run = _run_two_stage
    _INSTALLED = True
