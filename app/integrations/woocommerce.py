from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.request import Request
from uuid import uuid4

from app.integrations.wordpress import IntegrationError, ReadOnlyHttpClient, sanitize_text


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
        self, product_id: int, *, page: int = 1, per_page: int = 100, **filters: Any
    ) -> list[Mapping[str, Any]]:
        result = self.get(
            f"/wp-json/wc/v3/products/{int(product_id)}/variations",
            {"page": page, "per_page": per_page, **filters},
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

    def update_variations_prices(
        self, product_id: int, updates: list[Mapping[str, Any]], *, authorized: bool = False
    ) -> list[Mapping[str, Any]]:
        """Escrita estreita: altera somente preços de variações via batch WooCommerce."""
        if not authorized:
            raise IntegrationError("Atualização de preços não autorizada")
        sanitized: list[dict[str, str | int]] = []
        for item in updates:
            keys = set(item)
            if not keys <= {"id", "regular_price", "sale_price"} or "id" not in keys:
                raise IntegrationError("Payload de preço fora do escopo permitido")
            sanitized.append({
                "id": int(item["id"]),
                "regular_price": str(item.get("regular_price", "")),
                "sale_price": str(item.get("sale_price", "")),
            })
        if not sanitized:
            return []
        url = (
            self.base_url.rstrip("/")
            + f"/wp-json/wc/v3/products/{int(product_id)}/variations/batch"
        )
        body = json.dumps({"update": sanitized}).encode("utf-8")
        request = Request(url, data=body, method="POST", headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._authorization(),
            "User-Agent": "CrapScraper-controlled-pricing/1.0",
        })
        try:
            status, _headers, response_body = self.transport(request, self.timeout)
            if status >= 400:
                raise IntegrationError(f"WooCommerce recusou os preços: HTTP {status}")
            decoded = json.loads(response_body) if response_body else {}
        except Exception as error:
            if isinstance(error, IntegrationError):
                raise
            safe = sanitize_text(error, self.username, self.password)
            raise IntegrationError(f"Falha ao atualizar preços: {safe}") from None
        if not isinstance(decoded, Mapping):
            raise IntegrationError("WooCommerce retornou resposta inválida ao atualizar preços")
        return [item for item in decoded.get("update", []) or [] if isinstance(item, Mapping)]

    def update_product_prices(
        self, product_id: int, regular_price: str, sale_price: str, *, authorized: bool = False
    ) -> Mapping[str, Any]:
        """Escrita estreita: altera somente os dois preços do produto informado."""
        if not authorized:
            raise IntegrationError("Atualização de preços não autorizada")
        url = self.base_url.rstrip("/") + f"/wp-json/wc/v3/products/{int(product_id)}"
        body = json.dumps({
            "regular_price": str(regular_price), "sale_price": str(sale_price),
        }).encode("utf-8")
        request = Request(url, data=body, method="PUT", headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "Authorization": self._authorization(),
            "User-Agent": "CrapScraper-controlled-pack-pricing/1.0",
        })
        try:
            status, _headers, response_body = self.transport(request, self.timeout)
            if status >= 400:
                raise IntegrationError(f"WooCommerce recusou os preços: HTTP {status}")
            decoded = json.loads(response_body) if response_body else {}
        except Exception as error:
            if isinstance(error, IntegrationError):
                raise
            safe = sanitize_text(error, self.username, self.password)
            raise IntegrationError(f"Falha ao atualizar preços do pack: {safe}") from None
        if not isinstance(decoded, Mapping):
            raise IntegrationError("WooCommerce retornou resposta inválida ao atualizar o pack")
        return decoded

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
