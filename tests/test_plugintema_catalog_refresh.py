from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.plugintema_catalog import CatalogFilters, encode_catalog_csv
from app.plugintema_catalog_refresh import (
    infer_catalog_definition,
    refresh_catalog,
    save_catalog_definition,
    sync_product_cache,
)


def product(
    product_id: int,
    name: str,
    version: str,
    categories: list[str],
    *,
    status: str = "publish",
) -> dict:
    return {
        "id": product_id,
        "type": "variable",
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "permalink": f"https://plugintema.com.br/produto/{product_id}",
        "status": status,
        "categories": [{"id": index + 1, "name": value} for index, value in enumerate(categories)],
        "meta_data": [
            {"key": "pt_versao", "value": version},
            {"key": "site_oficial", "value": f"https://example.com/{product_id}"},
        ],
    }


class FakeWoo:
    def __init__(self, products: list[dict]) -> None:
        self.products = list(products)
        self.calls: list[dict] = []

    def list_products(self, *, page: int = 1, per_page: int = 100, **filters):
        self.calls.append({"page": page, "per_page": per_page, **filters})
        status = str(filters.get("status") or "")
        rows = [row for row in self.products if str(row.get("status") or "") == status]
        start = (page - 1) * per_page
        return rows[start:start + per_page]


class OptionalStatusFailingWoo(FakeWoo):
    def list_products(self, *, page: int = 1, per_page: int = 100, **filters):
        if str(filters.get("status") or "") in {"pending", "trash"}:
            raise RuntimeError("status não suportado neste proxy")
        return super().list_products(page=page, per_page=per_page, **filters)


class PluginTemaCatalogRefreshTests(unittest.TestCase):
    def test_legacy_plugin_catalog_infers_native_plugin_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugintema-plugin-20260819-215600-123456.csv"
            path.write_bytes(encode_catalog_csv([
                {
                    "ID": "1", "Tipo": "variable", "Nome": "SEO Plugin", "Slug": "seo-plugin",
                    "URL": "https://example/1", "Status": "publish",
                    "Metadado: pt_versao": "1.0.0", "Metadado: site_oficial": "",
                    "Categorias": "Plugins, SEO",
                }
            ]))
            mode, filters = infer_catalog_definition(path)
            self.assertEqual(mode, "plugin")
            self.assertEqual(filters.kinds, ("plugin",))
            self.assertEqual(filters.statuses, ("publish",))
            self.assertEqual(filters.categories, ())
            self.assertEqual(filters.version, "all")

    def test_second_cache_sync_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "products.json"
            t0 = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
            woo = FakeWoo([product(1, "AffiliateWP", "2.35.4", ["Plugins"])])
            products, first = sync_product_cache(woo, cache_path=cache, force_full=True, now=t0)
            self.assertEqual(first["mode"], "full")
            self.assertEqual(len(products), 1)

            woo.calls.clear()
            woo.products = [
                product(1, "AffiliateWP", "2.36.0", ["Plugins"]),
                product(2, "New Plugin", "1.0.0", ["Plugins"]),
            ]
            products, second = sync_product_cache(woo, cache_path=cache, now=t0 + timedelta(minutes=10))
            self.assertEqual(second["mode"], "incremental")
            self.assertEqual(len(products), 2)
            self.assertTrue(any(call.get("modified_after") for call in woo.calls))

    def test_optional_status_failure_does_not_break_full_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "products.json"
            woo = OptionalStatusFailingWoo([
                product(1, "Plugin publicado", "1.0.0", ["Plugins"]),
                product(2, "Plugin rascunho", "1.0.0", ["Plugins"], status="draft"),
            ])
            products, result = sync_product_cache(
                woo,
                cache_path=cache,
                force_full=True,
                now=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(result["mode"], "full")
            self.assertEqual({int(row["id"]) for row in products}, {1, 2})

    def test_refresh_preserves_saved_kind_category_and_status_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "plugintema-custom-seo-20260824-120000-123456.csv"
            catalog.write_bytes(encode_catalog_csv([
                {
                    "ID": "1", "Tipo": "variable", "Nome": "SEO One", "Slug": "seo-one",
                    "URL": "https://example/1", "Status": "publish",
                    "Metadado: pt_versao": "1.0.0", "Metadado: site_oficial": "",
                    "Categorias": "Plugins, SEO",
                }
            ]))
            save_catalog_definition(
                catalog,
                "custom",
                CatalogFilters(
                    kinds=("plugin",), categories=("SEO",), statuses=("publish",),
                    query="", product_ids=(), version="all",
                ),
            )
            woo = FakeWoo([
                product(1, "SEO One", "1.2.0", ["Plugins", "SEO"]),
                product(2, "Security Plugin", "1.0.0", ["Plugins", "Security"]),
                product(3, "SEO Theme", "4.0.0", ["Temas", "SEO"]),
                product(4, "SEO Draft", "1.0.0", ["Plugins", "SEO"], status="draft"),
            ])
            result = refresh_catalog(
                catalog,
                woo,
                force_full=True,
                cache_path=root / "cache.json",
            )
            self.assertEqual(result["after"], 1)
            self.assertEqual(result["versions_updated"], 1)
            self.assertEqual(result["filters"]["categories"], ["SEO"])
            with catalog.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["ID"] for row in rows], ["1"])
            self.assertEqual(rows[0]["Metadado: pt_versao"], "1.2.0")


if __name__ == "__main__":
    unittest.main()
