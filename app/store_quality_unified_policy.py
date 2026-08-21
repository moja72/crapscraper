from __future__ import annotations

import html as html_lib
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import uuid4

import app.store_custom_fields_quality_policy as quality
import app.web as web
from app.integrations.woocommerce import metadata_value

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_quality_unified.js"
_DESCRIPTION_KEY = "description"
_DESCRIPTION_LABEL = "Breve descrição"
_PRODUCT_FIELDS = "id,name,type,status,categories,permalink,meta_data,variations,short_description"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _plain_short_description(product: Mapping[str, Any]) -> str:
    raw = html_lib.unescape(str(product.get("short_description", "") or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(raw.replace("\xa0", " ").split()).strip()


def _product_values(product: Mapping[str, Any]) -> dict[str, str]:
    return {
        "version": _clean(metadata_value(product, "pt_versao")),
        "developer": _clean(metadata_value(product, "desenvolvedor")),
        "official": _clean(metadata_value(product, "site_oficial")),
        _DESCRIPTION_KEY: _plain_short_description(product),
    }


def _published_search_batches(woo: Any, query: str):
    """Busca no servidor quando há termo; ID numérico usa leitura direta."""
    normalized = _clean(query)
    if normalized.isdigit():
        product_id = int(normalized)
        try:
            reader = getattr(woo, "get_product_fresh", None) or getattr(woo, "get_product")
            product = reader(product_id)
            if isinstance(product, Mapping) and str(product.get("status", "publish") or "publish") == "publish":
                yield 1, [product]
                return
        except Exception:
            pass

    page = 1
    while True:
        batch = list(
            woo.list_products(
                page=page,
                per_page=100,
                status="publish",
                search=normalized,
                _fields=_PRODUCT_FIELDS,
            )
            or []
        )
        yield page, batch
        if len(batch) < 100:
            break
        page += 1


def _full_catalog_batches(woo: Any):
    page = 1
    while True:
        batch = list(
            woo.list_products(
                page=page,
                per_page=100,
                status="publish",
                _fields=_PRODUCT_FIELDS,
            )
            or []
        )
        yield page, batch
        if len(batch) < 100:
            break
        page += 1


def products_missing_custom_fields(
    woo: Any,
    query: str = "",
    *,
    selected_fields: Any = None,
    match_mode: str = "any",
    category_mode: str = "all",
    variation_mode: str = "all",
    progress: Callable[[int, int, int, str], None] | None = None,
    variation_progress: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Audita Plugins/Temas e, quando há busca, também retorna itens completos."""
    fields = quality._selected_fields(selected_fields)
    mode = quality._match_mode(match_mode)
    category_filter = quality._category_mode(category_mode)
    variation_filter = quality._variation_mode(variation_mode)
    normalized_query = _clean(query)
    search_mode = bool(normalized_query)
    batches = _published_search_batches(woo, normalized_query) if search_mode else _full_catalog_batches(woo)

    candidates: list[dict[str, Any]] = []
    examined = 0
    for page, batch in batches:
        for product in batch:
            if not isinstance(product, Mapping):
                continue
            if _clean(product.get("type")).casefold() != "variable":
                continue
            if not quality._has_child_variations(product):
                continue

            kind = quality._catalog_kind(product)
            if not kind:
                continue
            if category_filter == "root_only" and not quality._root_category_only(product, kind):
                continue

            examined += 1
            product_id = int(product.get("id") or 0)
            product_name = _clean(product.get("name"))
            values = _product_values(product)
            missing = [key for key in fields if not values.get(key)]
            qualifies = bool(missing) if mode == "any" else len(missing) == len(fields)

            # Uma busca explícita é também uma inspeção: o produto deve aparecer
            # mesmo quando todos os campos selecionados estiverem preenchidos.
            if not search_mode and not qualifies:
                continue

            candidates.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "product_type": _clean(product.get("type")),
                    "catalog_kind": kind,
                    "categories": quality._category_names(product),
                    "root_category_only": quality._root_category_only(product, kind),
                    "permalink": _clean(product.get("permalink")),
                    "values": values,
                    "missing_fields": missing,
                    "missing_labels": [quality._FIELDS[key][1] for key in missing],
                    "variation_count": len(product.get("variations", []) or []),
                    "standard_terms": [],
                    "standard_labels": [],
                    "nonstandard_variation_count": 0,
                    "nonstandard_variations": [],
                    "search_match": search_mode,
                }
            )

        if progress:
            current_name = _clean(batch[-1].get("name")) if batch and isinstance(batch[-1], Mapping) else ""
            progress(page, examined, len(candidates), current_name)

    if variation_filter != "all" and candidates:
        enriched: list[dict[str, Any]] = []
        workers = min(12, max(1, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="store-quality-variations") as executor:
            future_map = {
                executor.submit(quality._load_variation_summary, woo, int(item["product_id"])): item
                for item in candidates
            }
            total = len(future_map)
            for completed, future in enumerate(as_completed(future_map), start=1):
                item = future_map[future]
                summary = future.result()
                item.update(summary)
                if quality._variation_summary_matches(summary, variation_filter):
                    enriched.append(item)
                if variation_progress:
                    variation_progress(completed, total, _clean(item.get("product_name")))
        candidates = enriched

    candidates.sort(key=lambda item: (_clean(item.get("product_name")).casefold(), int(item.get("product_id") or 0)))
    return candidates


def _start_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    query = _clean(payload.get("query"))
    fields = quality._selected_fields(payload.get("selected_fields"))
    mode = quality._match_mode(payload.get("match_mode"))
    category_filter = quality._category_mode(payload.get("category_mode"))
    variation_filter = quality._variation_mode(payload.get("variation_mode"))
    job_id = uuid4().hex
    search_mode = bool(query)

    with quality._JOB_LOCK:
        if quality._JOB.get("status") == "running":
            raise ValueError("Já existe uma verificação de qualidade em andamento.")
        quality._JOB.update(
            {
                "job_id": job_id,
                "status": "running",
                "phase": "catalog",
                "page": 0,
                "examined": 0,
                "found": 0,
                "variation_completed": 0,
                "variation_total": 0,
                "current_product": "",
                "query": query,
                "search_mode": search_mode,
                "selected_fields": list(fields),
                "match_mode": mode,
                "category_mode": category_filter,
                "variation_mode": variation_filter,
                "products": [],
                "message": "Buscando produto diretamente no WooCommerce…" if search_mode else "Iniciando auditoria de Plugins e Temas variáveis…",
                "error": "",
            }
        )

    def progress(page: int, examined: int, found: int, current_product: str) -> None:
        with quality._JOB_LOCK:
            quality._JOB.update(
                {
                    "phase": "catalog",
                    "page": page,
                    "examined": examined,
                    "found": found,
                    "current_product": current_product,
                    "message": (
                        f"Busca direta: {examined} resultado(s) elegível(is) analisado(s)."
                        if search_mode
                        else f"Página {page}: {examined} Plugins/Temas variáveis verificados; {found} com pendências."
                    ),
                }
            )

    def variation_progress(completed: int, total: int, current_product: str) -> None:
        with quality._JOB_LOCK:
            quality._JOB.update(
                {
                    "phase": "variations",
                    "variation_completed": completed,
                    "variation_total": total,
                    "current_product": current_product,
                    "message": f"Variações filhas: {completed} de {total} produtos analisados.",
                }
            )

    def run() -> None:
        try:
            products = products_missing_custom_fields(
                web._build_store_woocommerce_client(),
                query,
                selected_fields=fields,
                match_mode=mode,
                category_mode=category_filter,
                variation_mode=variation_filter,
                progress=progress,
                variation_progress=variation_progress,
            )
            with quality._JOB_LOCK:
                quality._JOB.update(
                    {
                        "status": "completed",
                        "phase": "completed",
                        "products": products,
                        "found": len(products),
                        "message": (
                            f"Busca concluída: {len(products)} produto(s) encontrado(s)."
                            if search_mode
                            else f"Auditoria concluída: {quality._JOB.get('examined', 0)} Plugins/Temas variáveis verificados."
                        ),
                    }
                )
        except Exception as error:
            with quality._JOB_LOCK:
                quality._JOB.update({"status": "error", "phase": "error", "message": str(error), "error": str(error)})

    threading.Thread(target=run, name="store-quality-unified-scan", daemon=True).start()
    return quality._job_snapshot()


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    page = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return page
    block = f"\n<script data-store-quality-unified>\n{script}\n</script>\n"
    return page.replace("</body>", block + "</body>", 1) if "</body>" in page else page + block


def install_store_quality_unified_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    quality._FIELDS[_DESCRIPTION_KEY] = ("__short_description__", _DESCRIPTION_LABEL)
    quality._DEFAULT_FIELDS = tuple(quality._FIELDS)
    quality.products_missing_custom_fields = products_missing_custom_fields
    quality._start_job = _start_job

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
