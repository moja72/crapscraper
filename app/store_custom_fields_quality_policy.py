from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import app.web as web
from app.integrations.woocommerce import metadata_value

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

_JOB_LOCK = threading.RLock()
_JOB: dict[str, Any] = {
    "job_id": "",
    "status": "idle",
    "page": 0,
    "examined": 0,
    "found": 0,
    "current_product": "",
    "query": "",
    "selected_fields": list(_DEFAULT_FIELDS),
    "match_mode": "any",
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
    return " ".join(re.findall(r"[a-z0-9]+", _clean(value).casefold()))


def _selected_fields(value: Any) -> tuple[str, ...]:
    raw = value if isinstance(value, (list, tuple, set)) else ()
    selected = tuple(dict.fromkeys(str(item).strip().lower() for item in raw if str(item).strip().lower() in _FIELDS))
    return selected or _DEFAULT_FIELDS


def _match_mode(value: Any) -> str:
    return "all" if str(value or "").strip().lower() == "all" else "any"


def products_missing_custom_fields(
    woo: Any,
    query: str = "",
    *,
    selected_fields: Any = None,
    match_mode: str = "any",
    progress: Callable[[int, int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Lista produtos publicados com metadados obrigatórios ausentes."""
    fields = _selected_fields(selected_fields)
    mode = _match_mode(match_mode)
    folded_query = _fold(query)

    missing_products: list[dict[str, Any]] = []
    page = 1
    examined = 0

    while True:
        batch = list(
            woo.list_products(
                page=page,
                per_page=100,
                status="publish",
                _fields="id,name,type,categories,permalink,meta_data",
            )
            or []
        )

        for product in batch:
            if not isinstance(product, Mapping):
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

            missing_products.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "product_type": _clean(product.get("type")),
                    "categories": [
                        _clean(item.get("name"))
                        for item in product.get("categories", []) or []
                        if isinstance(item, Mapping) and _clean(item.get("name"))
                    ],
                    "permalink": _clean(product.get("permalink")),
                    "values": values,
                    "missing_fields": missing,
                    "missing_labels": [_FIELDS[key][1] for key in missing],
                }
            )

        if progress:
            current_name = _clean(batch[-1].get("name")) if batch and isinstance(batch[-1], Mapping) else ""
            progress(page, examined, len(missing_products), current_name)

        if len(batch) < 100:
            break
        page += 1

    missing_products.sort(key=lambda item: (_clean(item.get("product_name")).casefold(), int(item.get("product_id") or 0)))
    return missing_products


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
    job_id = uuid4().hex

    with _JOB_LOCK:
        if _JOB.get("status") == "running":
            raise ValueError("Já existe uma verificação de campos personalizados em andamento.")
        _JOB.update(
            {
                "job_id": job_id,
                "status": "running",
                "page": 0,
                "examined": 0,
                "found": 0,
                "current_product": "",
                "query": query,
                "selected_fields": list(fields),
                "match_mode": mode,
                "products": [],
                "message": "Iniciando varredura dos campos personalizados…",
                "error": "",
            }
        )

    def progress(page: int, examined: int, found: int, current_product: str) -> None:
        with _JOB_LOCK:
            _JOB.update(
                {
                    "page": page,
                    "examined": examined,
                    "found": found,
                    "current_product": current_product,
                    "message": f"Página {page}: {examined} produtos verificados; {found} com campos ausentes.",
                }
            )

    def run() -> None:
        try:
            products = products_missing_custom_fields(
                web._build_store_woocommerce_client(),
                query,
                selected_fields=fields,
                match_mode=mode,
                progress=progress,
            )
            with _JOB_LOCK:
                _JOB.update(
                    {
                        "status": "completed",
                        "products": products,
                        "found": len(products),
                        "message": f"Varredura concluída: {_JOB.get('examined', 0)} produtos verificados.",
                    }
                )
        except Exception as error:
            with _JOB_LOCK:
                _JOB.update(
                    {
                        "status": "error",
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
