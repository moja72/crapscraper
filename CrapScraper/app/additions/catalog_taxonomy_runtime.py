from __future__ import annotations

from typing import Any

_INSTALLED = False


def canonical_category(job: dict[str, Any]) -> str:
    """Return the only catalog category allowed during the current rollout."""
    return "Plugin" if str(job.get("kind") or "").strip().casefold() == "plugin" else "Tema"


def canonicalize_job_taxonomy(job: dict[str, Any]) -> dict[str, Any]:
    clean = dict(job)
    clean["categories"] = [canonical_category(job)]
    clean["tags"] = []
    return clean


def install_catalog_taxonomy_contract() -> None:
    """Keep WooCommerce taxonomy deliberately minimal for new additions.

    ChatGPT may still return suggestions because older cached descriptions can
    contain them, but the WooCommerce payload always receives exactly one category
    based on product kind and receives no tags. This also repairs retries of jobs
    prepared before this rule existed.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_catalog_taxonomy_contract", False):
        _INSTALLED = True
        return

    original_parent_payload = AdditionStoreGateway._parent_payload

    def parent_payload(self: Any, job: dict[str, Any], media_id: int, image_url: str = "", *, status: str = "draft"):
        return original_parent_payload(
            self,
            canonicalize_job_taxonomy(job),
            media_id,
            image_url,
            status=status,
        )

    AdditionStoreGateway._parent_payload = parent_payload
    AdditionStoreGateway._crapscraper_catalog_taxonomy_contract = True
    _INSTALLED = True


__all__ = [
    "canonical_category",
    "canonicalize_job_taxonomy",
    "install_catalog_taxonomy_contract",
]
