from __future__ import annotations

import os
from typing import Any

_INSTALLED = False

_CATEGORY_IDS = {
    "plugin": 504,
    "theme": 525,
}


def canonical_category(job: dict[str, Any]) -> str:
    return "Plugin" if str(job.get("kind") or "").strip().casefold() == "plugin" else "Tema"


def canonical_category_id(job: dict[str, Any]) -> int:
    kind = str(job.get("kind") or "").strip().casefold()
    return _CATEGORY_IDS["plugin" if kind == "plugin" else "theme"]


def canonicalize_job_taxonomy(job: dict[str, Any]) -> dict[str, Any]:
    clean = dict(job)
    clean["categories"] = [canonical_category(job)]
    clean["category_ids"] = [canonical_category_id(job)]
    clean["tags"] = []
    return clean


def install_catalog_taxonomy_contract() -> None:
    """Use the two existing PluginTema product categories by immutable ID.

    New additions must never create/resolve arbitrary WooCommerce terms here:
    plugin -> Plugin (#504), theme -> Tema (#525), and no tags.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_catalog_taxonomy_contract_v2", False):
        _INSTALLED = True
        return

    def parent_payload(
        self: Any,
        job: dict[str, Any],
        media_id: int,
        image_url: str = "",
        *,
        status: str = "draft",
    ) -> dict[str, Any]:
        clean = canonicalize_job_taxonomy(job)
        attribute = int(os.getenv("SCRAPER_WOOCOMMERCE_PLAN_ATTRIBUTE_ID", "4"))
        images = (
            [{"id": int(media_id)}]
            if int(media_id or 0)
            else ([{"src": str(image_url)}] if str(image_url or "").strip() else [])
        )
        if not images:
            raise RuntimeError("Imagem principal não disponível para criação do produto")

        return {
            "name": clean["product_name"],
            "type": "variable",
            "status": status,
            "description": clean["content"],
            "short_description": clean["short_description"],
            "categories": [{"id": canonical_category_id(clean)}],
            "tags": [],
            "images": images,
            "attributes": [
                {
                    "id": attribute,
                    "visible": True,
                    "variation": True,
                    "options": ["Anual", "Vitalício"],
                }
            ],
            "meta_data": [
                {"key": "pt_versao", "value": clean["source_version"]},
                {"key": "site_oficial", "value": clean["official_url"]},
                {"key": "desenvolvedor", "value": clean["developer"]},
                {"key": "crapscraper_addition_job", "value": clean["job_id"]},
                {"key": "fonte_crapscraper", "value": clean["source_name"]},
            ],
        }

    AdditionStoreGateway._parent_payload = parent_payload
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract = True
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract_v2 = True
    _INSTALLED = True


__all__ = [
    "canonical_category",
    "canonical_category_id",
    "canonicalize_job_taxonomy",
    "install_catalog_taxonomy_contract",
]
