from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_final_validation_policy as final_validation
import app.addition_full_product_creation_policy as full_product
import app.addition_parallel_generation_policy as parallel
import app.addition_product_creative_policy as creative
import app.new_product_workflow_policy as additions
from app.store_pricing import variation_period


_INSTALLED = False
_BASE_SEND_MESSAGE = None

_LICENSE_TERMS = {
    "annual": {"id": 798, "slug": "1-ano", "name": "1 ano"},
    "lifetime": {"id": 799, "slug": "vitalicio", "name": "vitalício"},
}


def _fold(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    return " ".join(re.findall(r"[a-z0-9]+", text.translate(replacements)))


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _short_description_prompt(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    kind = "tema WordPress" if _kind(job) == "theme" else "plugin WordPress"
    marketplace = parallel._expected_marketplace(job)
    return f"""Pesquise e escreva SOMENTE a breve descrição comercial deste produto para a PluginTema.

Produto: {name}
Tipo: {kind}
Fonte oficial esperada: {marketplace}

Use a fonte oficial ou resultados públicos confiáveis para confirmar a finalidade do produto. Escreva um único parágrafo em português do Brasil, com cerca de 400 a 500 caracteres e 2 ou 3 frases. Comece pelo principal benefício, explique o que o produto ajuda a fazer e termine indicando para quem ele é útil. Não invente recursos e não inclua versão, título, listas, SEO, tags, links, códigos ou explicações.

Responda SOMENTE com o parágrafo final."""


def _short_image_prompt(job: Mapping[str, Any]) -> str:
    name = str(job.get("source_name") or job.get("title") or "produto WordPress").strip()
    marketplace = parallel._expected_marketplace(job)
    if _kind(job) == "theme":
        visual = (
            "Use o arquivo anexado apenas como referência de mockup. Gere uma NOVA imagem 1:1 com fundo transparente, "
            "monitor Apple e celular inteiros. Mostre nas telas a aparência real do tema pesquisado; não reutilize as telas, "
            "cores ou marca da referência."
        )
    else:
        visual = (
            "Use o arquivo anexado apenas como referência da caixa 3D. Gere uma NOVA imagem 1:1 com fundo transparente, "
            "caixa profissional com pelo menos 3 faces visíveis e identidade real do plugin pesquisado. Use Quicksand e mostre "
            "\"Vitalício | Ilimitado | Atualizado\". Não reutilize a marca, cores ou arte da referência."
        )
    return f"""Gere SOMENTE a imagem principal deste produto para a PluginTema.

Produto: {name}
Fonte oficial esperada: {marketplace}

Pesquise o produto exato e use previews, screenshots e imagens públicas confiáveis para confirmar sua identidade visual. Se a página oficial não abrir, continue pela pesquisa pública; não peça arquivos e não responda com explicações.

{visual}

Entregue uma única imagem final, nova, profissional e pronta para e-commerce."""


def _all_image_sources(page: Any) -> set[str]:
    try:
        result = page.evaluate(
            """() => [...document.images]
              .map(img => String(img.currentSrc || img.src || ''))
              .filter(Boolean)"""
        )
        return {str(item or "").strip() for item in (result or []) if str(item or "").strip()}
    except Exception:
        return set()


def _is_image_prompt(prompt: str) -> bool:
    text = _fold(prompt)
    return "gere somente a imagem principal" in text or "imagem principal deste produto" in text


def _send_message_with_complete_image_baseline(context: Any, page: Any, prompt: str, job_id: str, url: str):
    before_all = _all_image_sources(page) if _is_image_prompt(prompt) else set()
    current, count, before = _BASE_SEND_MESSAGE(context, page, prompt, job_id, url)
    if before_all:
        before = set(before or set()) | before_all | _all_image_sources(current)
    return current, count, set(before or set())


def _strict_assistant_image_candidates(page: Any, before: set[str]) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """
            (before) => {
              const seen = new Set(before || []);
              const main = document.querySelector('main') || document.body;
              return [...main.querySelectorAll('img')].map((img, index) => {
                const turn = img.closest('[data-testid*="conversation-turn"], article');
                const roleNode = img.closest('[data-message-author-role]') ||
                  (turn && (turn.matches('[data-message-author-role]') ? turn : turn.querySelector('[data-message-author-role]')));
                const role = String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase();
                const text = String(turn?.innerText || '').trim().toLowerCase();
                const composer = !!img.closest('form, [data-testid*="composer"], #prompt-textarea');
                const generatedUi = /worked for|refined|editar|edit\b|share|compartilhar/.test(text);
                const promptLike = /gere somente a imagem principal|identificador interno|pesquisa visual|arquivo anexado/.test(text);
                return {
                  index,
                  src: String(img.currentSrc || img.src || ''),
                  width: Number(img.naturalWidth || 0),
                  height: Number(img.naturalHeight || 0),
                  role,
                  text,
                  composer,
                  generatedUi,
                  promptLike,
                  visible: !!(img.getClientRects().length && img.offsetWidth && img.offsetHeight),
                };
              }).filter(item => item.src && item.visible && item.width >= 256 && item.height >= 256 &&
                !seen.has(item.src) && !item.composer && item.role !== 'user' && !item.promptLike &&
                (item.role === 'assistant' || item.generatedUi) &&
                !item.src.includes('avatar') && !item.src.includes('icon'));
            }
            """,
            list(before or set()),
        )
    except Exception:
        return []
    rows = [dict(item) for item in (result or []) if isinstance(item, Mapping)]
    rows.sort(key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0), reverse=True)
    return rows


def _license_contract(woo: Any) -> dict[str, Any]:
    attrs = list(woo.get("/wp-json/wc/v3/products/attributes", {"per_page": 100}) or [])
    attr = next(
        (
            item for item in attrs
            if isinstance(item, Mapping)
            and (_fold(item.get("name")) == "licenca" or str(item.get("slug") or "").strip().lower() in {"pa_licenca", "licenca"})
        ),
        None,
    )
    if not attr or int(attr.get("id") or 0) <= 0:
        raise ValueError("O atributo global Licença (pa_licenca) não foi encontrado no WooCommerce.")
    attribute_id = int(attr.get("id") or 0)
    terms = list(woo.get(f"/wp-json/wc/v3/products/attributes/{attribute_id}/terms", {"per_page": 100}) or [])
    resolved: dict[str, Any] = {"attribute_id": attribute_id, "attribute_name": str(attr.get("name") or "Licença")}
    for period, expected in _LICENSE_TERMS.items():
        term = next((item for item in terms if isinstance(item, Mapping) and int(item.get("id") or 0) == expected["id"]), None)
        if not term:
            raise ValueError(f"O termo de Licença #{expected['id']} não foi encontrado no WooCommerce.")
        slug = str(term.get("slug") or "").strip().lower()
        name = str(term.get("name") or "").strip()
        if slug != expected["slug"] or _fold(name) != _fold(expected["name"]):
            raise ValueError(f"O termo de Licença #{expected['id']} não confere: esperado {expected['name']} ({expected['slug']}).")
        resolved[period] = {"id": expected["id"], "slug": slug, "name": name}
    return resolved


def _has_license_attribute(product: Mapping[str, Any]) -> bool:
    for item in product.get("attributes", []) or []:
        if not isinstance(item, Mapping):
            continue
        name = _fold(item.get("name"))
        slug = str(item.get("slug") or "").strip().lower()
        if name != "licenca" and slug not in {"pa_licenca", "licenca"}:
            continue
        if not bool(item.get("variation")):
            continue
        options = {_fold(value) for value in (item.get("options") or [])}
        return _fold("1 ano") in options and _fold("vitalício") in options
    return False


def _create_or_resume_draft_with_license(job_id: str, confirmation: str) -> dict[str, Any]:
    job = additions._recalculate_state(job_id)
    if confirmation.strip() != "CRIAR RASCUNHO":
        raise ValueError('Digite "CRIAR RASCUNHO" para confirmar a escrita no WooCommerce.')
    if job.get("state") not in {"ready_to_create", "draft_created", "error", "blocked"}:
        raise ValueError("O produto ainda precisa de conteúdo e ZIP válidos antes de criar o rascunho.")
    if not additions._content_complete(job):
        raise ValueError("Conteúdo incompleto.")
    if not Path(str(job.get("zip_path") or "")).exists():
        raise ValueError("ZIP preparado não está mais disponível.")

    woo = additions.web._build_store_woocommerce_client()
    contract = _license_contract(woo)
    existing_id = int(job.get("woo_product_id") or 0)
    if not existing_id:
        duplicate = additions._duplicate_product(woo, str(job.get("title") or job.get("source_name") or ""))
        if duplicate:
            additions._update(job_id, state="blocked", error=f"Produto com o mesmo nome já existe no WooCommerce: #{duplicate.get('id')}.")
            raise ValueError(f"Já existe um produto com o mesmo nome no WooCommerce: #{duplicate.get('id')}.")

    filename, download_url = additions._upload_zip(job)
    media_id = int(job.get("media_id") or 0)
    if not media_id and job.get("image_path"):
        media_id = additions._wp_media_upload(str(job.get("image_path")), str(job.get("title") or ""))

    category_id = additions._category_id(woo, str(job.get("kind") or "plugin"))
    title = str(job.get("title") or job.get("source_name") or "Novo produto")
    parent_attribute = {
        "id": contract["attribute_id"],
        "position": 0,
        "visible": True,
        "variation": True,
        "options": [contract["annual"]["name"], contract["lifetime"]["name"]],
    }

    if not existing_id:
        payload: dict[str, Any] = {
            "name": title,
            "type": "variable",
            "status": "draft",
            "description": str(job.get("description") or ""),
            "short_description": str(job.get("short_description") or ""),
            "attributes": [parent_attribute],
            "meta_data": [
                {"key": "pt_versao", "value": str(job.get("source_version") or "")},
                {"key": "crapscraper_source_url", "value": str(job.get("source_product_url") or "")},
                {"key": "crapscraper_addition_job", "value": job_id},
            ],
        }
        if category_id:
            payload["categories"] = [{"id": category_id}]
        if media_id:
            payload["images"] = [{"id": media_id}]
        product = additions._wc_request(woo, "POST", "/wp-json/wc/v3/products", payload)
        existing_id = int(product.get("id") or 0)
        if not existing_id:
            raise ValueError("WooCommerce não retornou o ID do rascunho criado.")
        additions._update(job_id, woo_product_id=existing_id, media_id=media_id)
    else:
        product = woo.get_product_fresh(existing_id)
        current_variations = list(woo.list_variations(existing_id, per_page=100) or [])
        if current_variations and not _has_license_attribute(product):
            raise ValueError("O rascunho existente usa um contrato antigo de variações. Exclua-o no WooCommerce e use Resetar para recriar com Licença.")
        if not _has_license_attribute(product):
            additions._wc_request(woo, "PUT", f"/wp-json/wc/v3/products/{existing_id}", {"type": "variable", "attributes": [parent_attribute]})

    existing_variations = list(woo.list_variations(existing_id, per_page=100) or [])
    periods = {variation_period(item) for item in existing_variations}
    unknown = [item for item in existing_variations if variation_period(item) not in {"annual", "lifetime"}]
    if unknown:
        raise ValueError("O rascunho possui variações fora do contrato Licença 1 ano/Vitalício; recrie o produto.")

    for period in ("annual", "lifetime"):
        if period in periods:
            continue
        term = contract[period]
        regular = additions._normalize(job.get(f"{period}_regular"))
        sale = additions._normalize(job.get(f"{period}_sale"))
        if not regular:
            raise ValueError(f"Preço original ausente para a licença {term['name']}.")
        variation_payload = {
            "regular_price": regular,
            "sale_price": sale,
            "downloadable": True,
            "virtual": True,
            "attributes": [{"id": contract["attribute_id"], "option": term["name"]}],
            "downloads": [{"name": filename, "file": download_url}],
        }
        additions._wc_request(woo, "POST", f"/wp-json/wc/v3/products/{existing_id}/variations", variation_payload)

    product = woo.get_product_fresh(existing_id)
    variations = list(woo.list_variations_fresh(existing_id, per_page=100) or [])
    if str(product.get("type") or "").lower() != "variable" or not _has_license_attribute(product):
        raise ValueError("O WooCommerce não confirmou o atributo global Licença no produto variável.")
    if len(variations) != 2 or {variation_period(item) for item in variations} != {"annual", "lifetime"}:
        raise ValueError("O produto precisa ter exatamente as duas licenças: 1 ano e vitalício.")

    job = additions._update(
        job_id,
        state="draft_created",
        woo_product_id=existing_id,
        media_id=media_id,
        remote_file_name=filename,
        remote_file_path=download_url,
        error="",
    )
    return {"ok": True, "message": f"Rascunho WooCommerce #{existing_id} criado com Licença 1 ano/Vitalício.", "job": additions._public_job(job)}


def install_addition_product_contract_policy() -> None:
    global _INSTALLED, _BASE_SEND_MESSAGE
    if _INSTALLED:
        return
    _BASE_SEND_MESSAGE = reconnect._send_message_resilient
    binding._description_only_prompt = _short_description_prompt
    parallel._parallel_image_prompt = _short_image_prompt
    creative._image_only_prompt = _short_image_prompt
    final_validation._description_prompt = _short_description_prompt
    final_validation._image_prompt = _short_image_prompt
    reconnect._send_message_resilient = _send_message_with_complete_image_baseline
    binding._assistant_image_candidates = _strict_assistant_image_candidates
    additions._create_or_resume_draft = _create_or_resume_draft_with_license
    full_product._has_plan_attribute = _has_license_attribute
    _INSTALLED = True
