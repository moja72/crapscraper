from __future__ import annotations

import re
import threading
import time
from typing import Any, Mapping

import app.new_product_workflow_policy as additions

_INSTALLED = False
_BASE_INITIALIZE = None
_BASE_PROMPT = None
_BASE_SAVE_CONTENT = None
_BASE_CREATE_DRAFT = None
_BASE_CATEGORY_ID = None
_BASE_WC_REQUEST = None
_CONTEXT = threading.local()
_CATEGORY_CACHE: tuple[float, list[dict[str, Any]]] = (0.0, [])


def _norm(value: Any) -> str:
    text = str(value or "").lower().strip()
    return " ".join(re.findall(r"[a-z0-9áàâãéèêíïóôõöúçñ]+", text, re.I))


def _ensure_column(connection: Any, name: str, declaration: str) -> None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(addition_jobs)").fetchall()}
    if name not in columns:
        connection.execute(f"ALTER TABLE addition_jobs ADD COLUMN {name} {declaration}")


def _patched_initialize(connection: Any) -> None:
    _BASE_INITIALIZE(connection)
    _ensure_column(connection, "category_name", "TEXT NOT NULL DEFAULT ''")


def _category_options() -> list[dict[str, Any]]:
    global _CATEGORY_CACHE
    now = time.time()
    cached_at, cached = _CATEGORY_CACHE
    if cached and now - cached_at < 300:
        return cached
    try:
        woo = additions.web._build_store_woocommerce_client()
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(woo.list_product_categories(page=page, per_page=100) or [])
            for item in batch:
                category_id = int(item.get("id") or 0)
                name = str(item.get("name") or "").strip()
                if category_id and name:
                    rows.append({"id": category_id, "name": name, "parent": int(item.get("parent") or 0)})
            if len(batch) < 100:
                break
            page += 1
        rows.sort(key=lambda item: str(item["name"]).casefold())
        _CATEGORY_CACHE = (now, rows)
        return rows
    except Exception:
        return cached


def _patched_prompt(job: Mapping[str, Any]) -> str:
    base = _BASE_PROMPT(job)
    categories = _category_options()
    options = [str(item.get("name") or "") for item in categories if str(item.get("name") or "").strip()][:100]
    category_block = ", ".join(options) if options else "Plugins ou Temas, conforme o tipo do produto"
    return (
        base
        + "\n\nCATEGORIA DO WOOCOMMERCE\n"
        + "Escolha a categoria existente mais específica e adequada. Não invente uma categoria nova. "
        + "Categorias disponíveis: "
        + category_block
        + ".\n\nNo bloco final estruturado, acrescente também a linha CATEGORIA: com exatamente o nome escolhido."
    )


def _patched_save_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    job_id = additions._normalize(payload.get("job_id"))
    previous_category = ""
    if job_id:
        try:
            previous_category = additions._normalize(additions._row(job_id).get("category_name"))
        except Exception:
            previous_category = ""
    result = _BASE_SAVE_CONTENT(payload)
    if job_id:
        category_name = (
            additions._normalize(payload.get("category_name"))
            if "category_name" in payload
            else previous_category
        )
        additions._update(job_id, category_name=category_name)
        job = additions._recalculate_state(job_id)
        result["job"] = additions._public_job(job)
    return result


def _find_specific_category(woo: Any, requested: str) -> int:
    wanted = _norm(requested)
    if not wanted:
        return 0
    page = 1
    while True:
        batch = list(woo.list_product_categories(page=page, per_page=100) or [])
        for item in batch:
            if _norm(item.get("name")) == wanted:
                return int(item.get("id") or 0)
        if len(batch) < 100:
            break
        page += 1
    return 0


def _patched_category_id(woo: Any, kind: str) -> int:
    requested = str(getattr(_CONTEXT, "category_name", "") or "").strip()
    if requested:
        category_id = _find_specific_category(woo, requested)
        if not category_id:
            raise ValueError(
                f'A categoria "{requested}" não existe mais no WooCommerce. Revise o conteúdo antes de criar o rascunho.'
            )
        return category_id
    return _BASE_CATEGORY_ID(woo, kind)


def _tag_ids(client: Any, raw_tags: str) -> list[int]:
    names = [part.strip() for part in re.split(r"[,;]", raw_tags or "") if part.strip()]
    ids: list[int] = []
    seen: set[str] = set()
    for name in names[:12]:
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            matches = list(client.get("/wp-json/wc/v3/products/tags", {"search": name, "per_page": 50}) or [])
        except Exception:
            matches = []
        tag_id = 0
        for item in matches:
            if _norm(item.get("name")) == key:
                tag_id = int(item.get("id") or 0)
                break
        if not tag_id:
            created = _BASE_WC_REQUEST(client, "POST", "/wp-json/wc/v3/products/tags", {"name": name})
            tag_id = int(created.get("id") or 0)
        if tag_id:
            ids.append(tag_id)
    return ids


def _patched_wc_request(client: Any, method: str, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = dict(payload)
    if method.upper() == "POST" and path.rstrip("/") == "/wp-json/wc/v3/products":
        raw_tags = str(getattr(_CONTEXT, "tags", "") or "")
        if raw_tags:
            ids = _tag_ids(client, raw_tags)
            if ids:
                data["tags"] = [{"id": tag_id} for tag_id in ids]
    return _BASE_WC_REQUEST(client, method, path, data)


def _patched_create_draft(job_id: str, confirmation: str) -> dict[str, Any]:
    job = additions._row(job_id)
    _CONTEXT.category_name = str(job.get("category_name") or "")
    _CONTEXT.tags = str(job.get("tags") or "")
    try:
        return _BASE_CREATE_DRAFT(job_id, confirmation)
    finally:
        _CONTEXT.category_name = ""
        _CONTEXT.tags = ""


def install_addition_content_enrichment_policy() -> None:
    global _INSTALLED, _BASE_INITIALIZE, _BASE_PROMPT, _BASE_SAVE_CONTENT
    global _BASE_CREATE_DRAFT, _BASE_CATEGORY_ID, _BASE_WC_REQUEST
    if _INSTALLED:
        return
    _BASE_INITIALIZE = additions._initialize
    _BASE_PROMPT = additions._prompt
    _BASE_SAVE_CONTENT = additions._save_content
    _BASE_CREATE_DRAFT = additions._create_or_resume_draft
    _BASE_CATEGORY_ID = additions._category_id
    _BASE_WC_REQUEST = additions._wc_request
    additions._initialize = _patched_initialize
    additions._prompt = _patched_prompt
    additions._save_content = _patched_save_content
    additions._create_or_resume_draft = _patched_create_draft
    additions._category_id = _patched_category_id
    additions._wc_request = _patched_wc_request
    _INSTALLED = True
