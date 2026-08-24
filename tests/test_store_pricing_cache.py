from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.store_pricing_cache import (
    get_pack_snapshot,
    get_plan_snapshot,
    patch_pack_product,
    patch_plan_prices,
    set_pack_snapshot,
    set_plan_snapshot,
)


class StorePricingCacheTests(unittest.TestCase):
    def cache_file(self, root: str) -> Path:
        return Path(root) / "store-pricing.json"

    def test_plan_snapshot_is_persisted_without_variation_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.store_pricing_cache.cache_path", return_value=self.cache_file(tmp)
        ):
            saved = set_plan_snapshot(
                ("plugin", "theme"),
                {
                    "ok": True,
                    "by_kind": {
                        "plugin": {
                            "product_count": 3,
                            "variation_count": 6,
                            "distribution": {"annual": [], "lifetime": []},
                        }
                    },
                    "variations": [{"id": 1}],
                },
            )
            self.assertTrue(saved["cache"]["saved"])
            loaded = get_plan_snapshot(("theme", "plugin"))
            self.assertIsNotNone(loaded)
            self.assertNotIn("variations", loaded)
            self.assertEqual(loaded["by_kind"]["plugin"]["product_count"], 3)

    def test_pack_write_through_updates_saved_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.store_pricing_cache.cache_path", return_value=self.cache_file(tmp)
        ):
            set_pack_snapshot([
                {
                    "product_id": 10,
                    "product_name": "Pack A",
                    "regular_price": "99.90",
                    "sale_price": "79.90",
                    "last_price": "79.90",
                }
            ])
            patch_pack_product({
                "product_id": 10,
                "product_name": "Pack A",
                "regular_price": "89.90",
                "sale_price": "69.90",
                "last_price": "69.90",
            })
            loaded = get_pack_snapshot()
            self.assertEqual(loaded["total"], 1)
            self.assertEqual(loaded["products"][0]["regular_price"], "89.90")
            self.assertEqual(loaded["cache"]["source"], "write-through")

    def test_bulk_price_write_through_keeps_plan_visible_without_remote_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.store_pricing_cache.cache_path", return_value=self.cache_file(tmp)
        ):
            set_plan_snapshot(
                ("plugin", "theme"),
                {
                    "ok": True,
                    "product_count": 6,
                    "variation_count": 12,
                    "distribution": {"annual": [], "lifetime": []},
                    "by_kind": {
                        "plugin": {
                            "product_count": 3,
                            "variation_count": 6,
                            "distribution": {
                                "annual": [{"regular_price": "10", "sale_price": "8", "count": 3}],
                                "lifetime": [{"regular_price": "20", "sale_price": "18", "count": 3}],
                            },
                        },
                        "theme": {
                            "product_count": 3,
                            "variation_count": 6,
                            "distribution": {
                                "annual": [{"regular_price": "10", "sale_price": "8", "count": 3}],
                                "lifetime": [{"regular_price": "20", "sale_price": "18", "count": 3}],
                            },
                        },
                    },
                },
            )
            patch_plan_prices(
                ("plugin", "theme"),
                {
                    "annual_regular": "49.90",
                    "annual_sale": "39.90",
                    "lifetime_regular": "149.90",
                    "lifetime_sale": "129.90",
                },
            )
            loaded = get_plan_snapshot(("plugin", "theme"))
            self.assertEqual(
                loaded["by_kind"]["plugin"]["distribution"]["annual"][0]["regular_price"],
                "49.90",
            )
            self.assertEqual(loaded["cache"]["source"], "write-through")


if __name__ == "__main__":
    unittest.main()
