from __future__ import annotations

import re
import threading
import unicodedata
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import uuid4

import app.web as web
from app.integrations.woocommerce import metadata_value
from app.plugintema_catalog import product_matches_catalog_kind

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MAKE_HANDLER: Callable[..., Any] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_custom_fields_quality.js"

_FIELDS: dict[str, tuple[str, str]] = {
    "version": ("pt_versao", "Versão"),
    "developer": ("desenvolvedor", "Desenvolvedor"),
    "official": ("site_oficial", "Link oficial"),
}
_DEFAULT_FIELDS = tuple(_FIELDS)
_ROOT_CATEGORY_ALIASES: dict[str, set[str]] = {
    "plugin": {"plugin", "plugins", "plugin wordpress", "plugins wordpress"},
    "theme": {"tema", "temas", "theme", "themes", "tema wordpress", "temas wordpress"},
}
_STANDARD_VARIATION_LABELS = {
    "annual": "1 ano",
    "lifetime": "Vitalício",
    "free": "Gratuito",
}

_JOB_LOCK = threading.RLock()
_JOB: dict[str, Any] = {
    "job_id": "",
    "status": "idle",
    "phase": "",
    "page": 0,
    "examined": 0,
    "found": 0,
    "variation_completed": 0,
    "variation_total": 0,
    "current_product": "",
    "query": "",
    "selected_fields": list(_DEFAULT_FIELDS),
    "match_mode": "any",
    "category_mode": "all",
    "variation_mode": "all",
    "products": [],
    "message": "",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return str(value).strip()
    return " ".join(str(value).split()).strip()


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _clean(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def _selected_fields(value: Any) -> tuple[str, ...]:
    raw = value if isinstance(value, (list, tuple, set)) else ()
    selected = tuple(
        dict.fromkeys(
            str(item).strip().lower()
            for item in raw
            if str(item).strip().lower() in _FIELDS
        )
    )
    return selected or _DEFAULT_FIELDS


def _match_mode(value: Any) -> str:
    return "all" if str(value or "").strip().lower() == "all" else "any"


def _category_mode(value: Any) -> str:
    return "root_only" if str(value or "").strip().lower() == "root_only" else "all"


def _variation_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"nonstandard", "none_standard"}:
        return normalized
    return "all"


def _category_names(product: Mapping[str, Any]) -> list[str]:
    return [
        _clean(item.get("name"))
        for item in product.get("categories", []) or []
        if isinstance(item, Mapping) and _clean(item.get("name"))
    ]


def _catalog_kind(product: Mapping[str, Any]) -> str:
    if product_matches_catalog_kind(product, "plugin"):
        return "plugin"
    if product_matches_catalog_kind(product, "theme"):
        return "theme"
    return ""


def _root_category_only(product: Mapping[str, Any], kind: str) -> bool:
    names = {_fold(name) for name in _category_names(product) if _fold(name)}
    allowed = _ROOT_CATEGORY_ALIASES.get(kind, set())
    return bool(names and allowed and names <= allowed)


def _has_child_variations(product: Mapping[str, Any]) -> bool:
    variations = product.get("variations", []) or []
    return isinstance(variations, (list, tuple)) and any(str(item).strip() for item in variations)


def _standard_terms_for_text(value: Any) -> set[str]:
    text = f" {_fold(value)} "
    matched: set[str] = set()
    annual_tokens = (" 1 ano ", " anual ", " annual ", " 12 meses ", " 12 mes ")
    lifetime_tokens = (" vitalicio ", " lifetime ", " perpetuo ", " perpetual ")
    free_tokens = (" gratuito ", " gratis ", " free ")
    if any(token in text for token in annual_tokens):
        matched.add("annual")
    if any(token in text for token in lifetime_tokens):
        matched.add("lifetime")
    if any(token in text for token in free_tokens):
        matched.add("free")
    return matched


def _variation_text(variation: Mapping[str, Any]) -> str:
    parts = [variation.get("name", ""), variation.get("sku", "")]
    parts.extend(
        item.get("option", "")
        for item in variation.get("attributes", []) or []
        if isinstance(item, Mapping)
    )
    return " ".join(_clean(part) for part in parts if _clean(part))


def _load_variation_summary(woo: Any, product_id: int) -> dict[str, Any]:
    variations = [
        item
        for item in (woo.list_variations(
            int(product_id),
            per_page=100,
            _fields="id,name,sku,attributes",
        ) or [])
        if isinstance(item, Mapping)
    ]
    recognized: set[str] = set()
    nonstandard: list[str] = []
    for variation in variations:
        raw = _variation_text(variation)
        terms = _standard_terms_for_text(raw)
        if terms:
            recognized.update(terms)
        else:
            nonstandard.append(raw or f"Variação #{variation.get('id', '')}")
    return {
        "variation_count": len(variations),
        "standard_terms": sorted(recognized),
        "standard_labels": [_STANDARD_VARIATION_LABELS[key] for key in ("annual", "lifetime", "free") if key in recognized],
        "nonstandard_variation_count": len(nonstandard),
        "nonstandard_variations": nonstandard[:12],
    }


def _variation_summary_matches(summary: Mapping[str, Any], mode: str) -> bool:
    if mode == "nonstandard":
        return int(summary.get("nonstandard_variation_count") or 0) > 0
    if mode == "none_standard":
        return not bool(summary.get("standard_terms"))
    return True


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
    """Lista apenas Plugins/Temas variáveis com filhos e metadados obrigatórios ausentes."""
    fields = _selected_fields(selected_fields)
    mode = _match_mode(match_mode)
    category_filter = _category_mode(category_mode)
    variation_filter = _variation_mode(variation_mode)
    folded_query = _fold(query)

    candidates: list[dict[str, Any]] = []
    page = 1
    examined = 0

    while True:
        batch = list(
            woo.list_products(
                page=page,
                per_page=100,
                status="publish",
                _fields="id,name,type,categories,permalink,meta_data,variations",
            )
            or []
        )

        for product in batch:
            if not isinstance(product, Mapping):
                continue
            if _clean(product.get("type")).casefold() != "variable":
                continue
            if not _has_child_variations(product):
                continue

            kind = _catalog_kind(product)
            if not kind:
                continue
            if category_filter == "root_only" and not _root_category_only(product, kind):
                continue

            examined += 1
            product_id = int(product.get("id") or 0)
            product_name = _clean(product.get("name"))
            searchable = _fold(f"{product_id} {product_name}")
            if folded_query and folded_query not in searchable:
                continue

            values = {
                key: _clean(metadata_value(product, meta_key))
                for key, (meta_key, _label) in _FIELDS.items()
            }
            missing = [key for key in fields if not values.get(key)]
            qualifies = bool(missing) if mode == "any" else len(missing) == len(fields)
            if not qualifies:
                continue

            candidates.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "product_type": _clean(product.get("type")),
                    "catalog_kind": kind,
                    "categories": _category_names(product),
                    "root_category_only": _root_category_only(product, kind),
                    "permalink": _clean(product.get("permalink")),
                    "values": values,
                    "missing_fields": missing,
                    "missing_labels": [_FIELDS[key][1] for key in missing],
                    "variation_count": len(product.get("variations", []) or []),
                    "standard_terms": [],
                    "standard_labels": [],
                    "nonstandard_variation_count": 0,
                    "nonstandard_variations": [],
                }
            )

        if progress:
            current_name = _clean(batch[-1].get("name")) if batch and isinstance(batch[-1], Mapping) else ""
            progress(page, examined, len(candidates), current_name)

        if len(batch) < 100:
            break
        page += 1

    if variation_filter != "all" and candidates:
        enriched: list[dict[str, Any]] = []
        workers = min(12, max(1, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="store-quality-variations") as executor:
            future_map = {
                executor.submit(_load_variation_summary, woo, int(item["product_id"])): item
                for item in candidates
            }
            total = len(future_map)
            for completed, future in enumerate(as_completed(future_map), start=1):
                item = future_map[future]
                summary = future.result()
                item.update(summary)
                if _variation_summary_matches(summary, variation_filter):
                    enriched.append(item)
                if variation_progress:
                    variation_progress(completed, total, _clean(item.get("product_name")))
        candidates = enriched

    candidates.sort(key=lambda item: (_clean(item.get("product_name")).casefold(), int(item.get("product_id") or 0)))
    return candidates


def _job_snapshot() -> dict[str, Any]:
    with _JOB_LOCK:
        return {
            **_JOB,
            "products": [dict(item) for item in _JOB.get("products", []) if isinstance(item, Mapping)],
            "selected_fields": list(_JOB.get("selected_fields", [])),
        }


def _start_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    query = _clean(payload.get("query"))
    fields = _selected_fields(payload.get("selected_fields"))
    mode = _match_mode(payload.get("match_mode"))
    category_filter = _category_mode(payload.get("category_mode"))
    variation_filter = _variation_mode(payload.get("variation_mode"))
    job_id = uuid4().hex

    with _JOB_LOCK:
        if _JOB.get("status") == "running":
            raise ValueError("Já existe uma verificação de campos personalizados em andamento.")
        _JOB.update(
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
                "selected_fields": list(fields),
                "match_mode": mode,
                "category_mode": category_filter,
                "variation_mode": variation_filter,
                "products": [],
                "message": "Iniciando varredura de Plugins e Temas variáveis…",
                "error": "",
            }
        )

    def progress(page: int, examined: int, found: int, current_product: str) -> None:
        with _JOB_LOCK:
            _JOB.update(
                {
                    "phase": "catalog",
                    "page": page,
                    "examined": examined,
                    "found": found,
                    "current_product": current_product,
                    "message": f"Página {page}: {examined} Plugins/Temas variáveis verificados; {found} com campos ausentes.",
                }
            )

    def variation_progress(completed: int, total: int, current_product: str) -> None:
        with _JOB_LOCK:
            _JOB.update(
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
            with _JOB_LOCK:
                _JOB.update(
                    {
                        "status": "completed",
                        "phase": "completed",
                        "products": products,
                        "found": len(products),
                        "message": f"Varredura concluída: {_JOB.get('examined', 0)} Plugins/Temas variáveis verificados.",
                    }
                )
        except Exception as error:
            with _JOB_LOCK:
                _JOB.update(
                    {
                        "status": "error",
                        "phase": "error",
                        "message": str(error),
                        "error": str(error),
                    }
                )

    threading.Thread(target=run, name="store-custom-fields-scan", daemon=True).start()
    return _job_snapshot()


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-store-custom-fields-quality>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _patched_make_handler(app: Any, *, include_inline_assets: bool = False):
    base_factory = _BASE_MAKE_HANDLER or web.make_handler
    BaseHandler = base_factory(app, include_inline_assets=include_inline_assets)

    class StoreCustomFieldsHandler(BaseHandler):
        def _route_get(self, path: str) -> bool:
            if path == "/loja/produtos/campos-ausentes":
                self._send_json({"ok": True, **_job_snapshot()})
                return True
            return super()._route_get(path)

        def _route_post(self, path: str, payload: dict[str, Any]) -> bool:
            if path == "/loja/produtos/campos-ausentes":
                try:
                    self._send_json({"ok": True, "started": True, **_start_job(payload)}, code=202)
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return True
            return super()._route_post(path, payload)

    return StoreCustomFieldsHandler


def install_store_custom_fields_quality_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_MAKE_HANDLER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    _BASE_MAKE_HANDLER = web.make_handler
    web.render_panel_page = _patched_render_panel_page
    web.make_handler = _patched_make_handler
    _INSTALLED = True
