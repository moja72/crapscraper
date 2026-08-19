from __future__ import annotations

from typing import Any

import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_CREATE_OR_RESUME_DRAFT = None


def _ensure_category_column() -> None:
    """Keep older local SQLite databases compatible with the simplified flow."""
    with additions._db() as connection:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(addition_jobs)").fetchall()
        }
        if "category_name" not in columns:
            connection.execute(
                "ALTER TABLE addition_jobs ADD COLUMN category_name TEXT NOT NULL DEFAULT ''"
            )


def _prepare_root_category(job_id: str) -> dict[str, Any]:
    _ensure_category_column()
    job = additions._row(job_id)
    kind = simple._kind(job)
    woo = additions.web._build_store_woocommerce_client()
    category_id, category_name = simple._root_category(woo, kind)
    if not category_id or not str(category_name or "").strip():
        label = "Tema" if kind == "theme" else "Plugin"
        raise RuntimeError(f"Categoria raiz {label} não encontrada no WooCommerce.")

    job = additions._update(
        job_id,
        category_name=str(category_name).strip(),
        error="",
    )
    one_click._emit(
        job_id,
        f"Categoria definida automaticamente pelo tipo do produto: {category_name}.",
        step="category",
        progress=86,
    )
    return job


def _create_or_resume_draft_with_root_category(job_id: str, confirmation: str) -> dict[str, Any]:
    _prepare_root_category(job_id)
    if not callable(_ORIGINAL_CREATE_OR_RESUME_DRAFT):
        raise RuntimeError("Fluxo base de criação do rascunho não está disponível.")
    return _ORIGINAL_CREATE_OR_RESUME_DRAFT(job_id, confirmation)


def install_addition_root_category_policy() -> None:
    global _INSTALLED, _ORIGINAL_CREATE_OR_RESUME_DRAFT
    if _INSTALLED:
        return
    _ORIGINAL_CREATE_OR_RESUME_DRAFT = additions._create_or_resume_draft
    additions._create_or_resume_draft = _create_or_resume_draft_with_root_category
    _INSTALLED = True
