from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from app.store_pricing import (
    apply_store_prices, build_store_pricing_snapshot, normalize_prices,
    read_store_price_reference_products, variation_period,
)


def product(product_id: int, category: str) -> dict:
    return {
        "id": product_id, "name": f"Produto {product_id}", "status": "publish",
        "categories": [{"name": category}],
    }


class Woo:
    def __init__(self) -> None:
        self.products = [product(10, "Plugins"), product(20, "Temas"), product(30, "Templates")]
        self.variations = {
            10: [
                {"id": 101, "attributes": [{"option": "Anual"}], "regular_price": "79.90", "sale_price": "59.90"},
                {"id": 102, "attributes": [{"option": "Vitalício"}], "regular_price": "149.90", "sale_price": ""},
            ],
            20: [{"id": 201, "name": "Licença Lifetime", "regular_price": "149.90", "sale_price": "129.90"}],
        }
        self.updates = []

    def list_products(self, **_kwargs):
        return self.products

    def list_variations(self, product_id, **_kwargs):
        return self.variations.get(product_id, [])

    def update_variations_prices(self, product_id, updates, *, authorized=False):
        assert authorized
        self.updates.append((product_id, updates))
        return updates


class StorePricingTests(unittest.TestCase):
    def test_period_recognizes_portuguese_and_english(self):
        self.assertEqual(variation_period({"attributes": [{"option": "Plano anual"}]}), "annual")
        self.assertEqual(variation_period({"name": "Licença Vitalícia"}), "lifetime")
        self.assertEqual(variation_period({"sku": "product-lifetime"}), "lifetime")

    def test_snapshot_filters_plugins_and_themes(self):
        snapshot = build_store_pricing_snapshot(Woo(), ("plugin", "theme"))
        self.assertEqual(snapshot["product_count"], 2)
        self.assertEqual(snapshot["variation_count"], 3)
        self.assertEqual(snapshot["unmatched_variation_count"], 0)
        self.assertEqual(snapshot["by_kind"]["plugin"]["product_count"], 1)
        self.assertEqual(snapshot["by_kind"]["plugin"]["variation_count"], 2)
        self.assertEqual(snapshot["by_kind"]["theme"]["product_count"], 1)
        self.assertEqual(snapshot["by_kind"]["theme"]["variation_count"], 1)

    def test_snapshot_can_use_local_reference_products_without_listing_woocommerce(self):
        woo = Woo()
        snapshot = build_store_pricing_snapshot(woo, ("plugin",), products=[woo.products[0]])
        self.assertEqual(snapshot["product_count"], 1)
        self.assertEqual(snapshot["by_kind"]["plugin"]["variation_count"], 2)

    def test_reference_products_are_read_from_imported_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugintema-selection.csv"
            path.write_text(
                "ID,Nome,Categorias\n10,Plugin A,Plugins\n20,Tema A,Temas\n",
                encoding="utf-8",
            )
            rows = read_store_price_reference_products(Path(directory), ("plugin", "theme"), limit_per_kind=1)
        self.assertEqual({row["id"] for row in rows}, {10, 20})

    def test_reference_products_can_read_complete_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plugintema-selection.csv"
            path.write_text(
                "ID,Nome,Categorias\n10,Plugin A,Plugins\n11,Plugin B,Plugins\n12,Plugin C,Plugins\n13,Plugin D,Plugins\n",
                encoding="utf-8",
            )
            rows = read_store_price_reference_products(Path(directory), ("plugin",), limit_per_kind=None)
        self.assertEqual({row["id"] for row in rows}, {10, 11, 12, 13})

    def test_prices_accept_brazilian_format_and_validate_promotion(self):
        prices = normalize_prices({
            "annual_regular": "R$ 79,90", "annual_sale": "59,90",
            "lifetime_regular": "149,90", "lifetime_sale": "",
        })
        self.assertEqual(prices["annual_regular"], "79.90")
        self.assertEqual(prices["lifetime_sale"], "")
        with self.assertRaises(ValueError):
            normalize_prices({
                "annual_regular": "50", "annual_sale": "60",
                "lifetime_regular": "100", "lifetime_sale": "",
            })

    def test_apply_updates_only_scoped_price_fields(self):
        woo = Woo()
        progress = []
        result = apply_store_prices(woo, {
            "kinds": ["plugin", "theme"], "confirmation": "ALTERAR PRECOS",
            "annual_regular": "80", "annual_sale": "60",
            "lifetime_regular": "150", "lifetime_sale": "130",
        }, progress=lambda phase, completed, total, *_detail: progress.append((phase, completed, total)))
        self.assertTrue(result["ok"])
        self.assertEqual(result["updated_variation_count"], 3)
        self.assertEqual({item["id"] for _, rows in woo.updates for item in rows}, {101, 102, 201})
        self.assertTrue(all(set(item) == {"id", "regular_price", "sale_price"} for _, rows in woo.updates for item in rows))
        self.assertIn(("reading", 2, 2), progress)
        self.assertIn(("updating", 2, 2), progress)
        self.assertEqual({product_id for product_id, _rows in woo.updates}, {10, 20})

    def test_panel_has_store_tab_on_opposite_edge(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        css = (root / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        nav = web.split('class="tabs-nav main-tabs-nav"', 1)[1].split('class="page-head-sticky"', 1)[0]
        self.assertLess(nav.index('id="tab_btn_adicoes"'), nav.index('class="main-tabs-spacer"'))
        self.assertLess(nav.index('class="main-tabs-spacer"'), nav.index('id="tab_btn_loja"'))
        self.assertIn("flex: 1 1 auto", css)
        self.assertIn('"loja"]', js)

    def test_panel_server_does_not_allow_duplicate_instances_on_same_port(self):
        from app.web import PTThreadingHTTPServer

        self.assertFalse(PTThreadingHTTPServer.allow_reuse_address)
        launcher = (Path(__file__).resolve().parents[1] / "autoscraper.bat").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8765/health", launcher)
        self.assertIn("Abrindo o painel existente", launcher)

    def test_store_prices_are_loaded_automatically_without_manual_button(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        css = (root / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        route = web.split('if path == "/loja/precos":', 1)[1].split(
            'if path == "/plugintema/catalogo/baixar":', 1
        )[0]
        self.assertNotIn('"deferred": True', route)
        self.assertNotIn('query.get("consultar")', route)
        self.assertIn("build_store_pricing_snapshot", route)
        self.assertIn("read_store_price_reference_products", route)
        self.assertNotIn('id="store_refresh_btn"', web)
        self.assertIn("storeKindPriceCard", js)
        self.assertIn("Somente leitura", js)
        self.assertNotIn("consultar=1", js)
        self.assertIn('if path == "/loja/precos/status":', web)
        self.assertIn("_start_store_price_job", web)
        self.assertIn("waitForStorePriceJob", js)
        self.assertIn('status.status === "completed"', js)
        self.assertIn("limit_per_kind=None", web)
        self.assertIn("started.job_id", js)
        self.assertIn("store-progress-track", css)
        self.assertIn("60 * 60 * 1000", js)
        self.assertIn("write_workers = min(4", (root / "app" / "store_pricing.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
