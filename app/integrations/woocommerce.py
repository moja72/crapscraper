from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from app.integrations.wordpress import ReadOnlyHttpClient


def metadata_value(product: Mapping[str, Any], key: str) -> Any:
    for item in product.get("meta_data", []) or []:
        if str(item.get("key", "")) == key:
            return item.get("value")
    return None


def pt_versao(product: Mapping[str, Any]) -> str:
    value = metadata_value(product, "pt_versao")
    return "" if value is None else str(value)


def variation_downloads(variation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.get("id", "")),
            "name": str(item.get("name", "")),
            "file": str(item.get("file", "")),
        }
        for item in variation.get("downloads", []) or []
        if isinstance(item, Mapping)
    ]


class WooCommerceClient(ReadOnlyHttpClient):
    def list_products(
        self, *, page: int = 1, per_page: int = 100, **filters: Any
    ) -> list[Mapping[str, Any]]:
        params = {"page": page, "per_page": per_page, **filters}
        return list(self.get("/wp-json/wc/v3/products", params) or [])

    def search_products(self, query: str, *, per_page: int = 20) -> list[Mapping[str, Any]]:
        return self.list_products(search=query, per_page=per_page)

    def list_product_categories(self, *, page: int = 1, per_page: int = 100) -> list[Mapping[str, Any]]:
        return list(self.get("/wp-json/wc/v3/products/categories", {"page": page, "per_page": per_page}) or [])

    def get_product(self, product_id: int) -> Mapping[str, Any]:
        return self.get(f"/wp-json/wc/v3/products/{int(product_id)}")

    def get_product_fresh(self, product_id: int) -> Mapping[str, Any]:
        """Read a product through a unique URL so private REST caches cannot replay it."""
        return self.get(
            f"/wp-json/wc/v3/products/{int(product_id)}",
            {"_crapscraper_fresh": uuid4().hex},
        )

    def list_variations(
        self, product_id: int, *, page: int = 1, per_page: int = 100
    ) -> list[Mapping[str, Any]]:
        result = self.get(
            f"/wp-json/wc/v3/products/{int(product_id)}/variations",
            {"page": page, "per_page": per_page},
        )
        return list(result or [])

    def list_variations_fresh(self, product_id: int, *, per_page: int = 100) -> list[Mapping[str, Any]]:
        result = self.get(
            f"/wp-json/wc/v3/products/{int(product_id)}/variations",
            {"page": 1, "per_page": per_page, "_crapscraper_fresh": uuid4().hex},
        )
        return list(result or [])

    def get_variation(self, product_id: int, variation_id: int) -> Mapping[str, Any]:
        return self.get(
            f"/wp-json/wc/v3/products/{int(product_id)}/variations/{int(variation_id)}"
        )

    @staticmethod
    def metadata(product: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return list(product.get("meta_data", []) or [])

    @staticmethod
    def version(product: Mapping[str, Any]) -> str:
        return pt_versao(product)

    @staticmethod
    def downloads(variation: Mapping[str, Any]) -> list[dict[str, Any]]:
        return variation_downloads(variation)

    @staticmethod
    def categories(product: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return list(product.get("categories", []) or [])

    @staticmethod
    def images(product: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return list(product.get("images", []) or [])

    create_product = ReadOnlyHttpClient.write
    update_product = ReadOnlyHttpClient.write
    delete_product = ReadOnlyHttpClient.write
    create_variation = ReadOnlyHttpClient.write
    update_variation = ReadOnlyHttpClient.write
    delete_variation = ReadOnlyHttpClient.write
