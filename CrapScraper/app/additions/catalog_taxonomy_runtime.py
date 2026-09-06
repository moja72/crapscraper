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


def _taxonomy_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "categories": [{"id": canonical_category_id(job)}],
        "tags": [],
    }


def _taxonomy_matches(product: dict[str, Any], job: dict[str, Any]) -> bool:
    category_ids = [int(item.get("id") or 0) for item in product.get("categories", []) or []]
    tags = list(product.get("tags", []) or [])
    return category_ids == [canonical_category_id(job)] and not tags


def install_catalog_taxonomy_contract() -> None:
    """Use only the two existing PluginTema categories by immutable ID.

    plugin -> Plugin (#504)
    theme  -> Tema (#525)
    tags   -> none

    The category is written in the initial product payload and then asserted with
    an explicit WooCommerce update. Final validation also refuses to mark a job
    completed if WooCommerce returns any extra/wrong category or any tag.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_catalog_taxonomy_contract_v3", False):
        _INSTALLED = True
        return

    original_create_parent = AdditionStoreGateway.create_parent
    original_update_parent = AdditionStoreGateway.update_parent
    original_validate = AdditionStoreGateway.validate

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

    def force_taxonomy(self: Any, product_id: int, job: dict[str, Any]) -> dict[str, Any]:
        product_id = int(product_id or 0)
        if not product_id:
            raise RuntimeError("WooCommerce não retornou produto para aplicar a categoria canônica")
        self._wc("PUT", f"/products/{product_id}", json=_taxonomy_payload(job))
        product = self._wc("GET", f"/products/{product_id}")
        if not _taxonomy_matches(product, job):
            expected = canonical_category(job)
            expected_id = canonical_category_id(job)
            raise RuntimeError(
                f"Taxonomia final divergiu: esperado somente {expected} (ID {expected_id}) e nenhuma tag"
            )
        return product

    def create_parent(self: Any, job: dict[str, Any], media_id: int, download_ref: str, image_url: str = ""):
        clean = canonicalize_job_taxonomy(job)
        product = original_create_parent(self, clean, media_id, download_ref, image_url)
        force_taxonomy(self, int(product.get("id") or 0), clean)
        return product

    def update_parent(self: Any, product_id: int, job: dict[str, Any], media_id: int, download_ref: str, image_url: str = ""):
        clean = canonicalize_job_taxonomy(job)
        product = original_update_parent(self, product_id, clean, media_id, download_ref, image_url)
        force_taxonomy(self, int(product_id), clean)
        return product

    def validate(self: Any, product_id: int, job: dict[str, Any], variation_ids: Any, expected_status: Any = None) -> bool:
        try:
            base_ok = original_validate(self, product_id, job, variation_ids, expected_status=expected_status)
        except TypeError:
            base_ok = original_validate(self, product_id, job, variation_ids)
        if not base_ok:
            return False
        product = self._wc("GET", f"/products/{int(product_id)}")
        return _taxonomy_matches(product, job)

    AdditionStoreGateway._parent_payload = parent_payload
    AdditionStoreGateway._force_catalog_taxonomy = force_taxonomy
    AdditionStoreGateway.create_parent = create_parent
    AdditionStoreGateway.update_parent = update_parent
    AdditionStoreGateway.validate = validate
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract = True
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract_v2 = True
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract_v3 = True
    _INSTALLED = True


__all__ = [
    "canonical_category",
    "canonical_category_id",
    "canonicalize_job_taxonomy",
    "install_catalog_taxonomy_contract",
]
