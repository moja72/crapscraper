from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.store_pricing_cache import get_pack_snapshot, get_plan_snapshot, set_pack_snapshot, set_plan_snapshot


class StorePricingCachePolicyContractTests(unittest.TestCase):
    def test_saved_plan_and_pack_data_survive_separate_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.store_pricing_cache.cache_path", return_value=Path(tmp) / "prices.json"
        ):
            set_plan_snapshot(("plugin", "theme"), {
                "ok": True,
                "by_kind": {"plugin": {"product_count": 2}, "theme": {"product_count": 2}},
            })
            set_pack_snapshot([
                {"product_id": 7, "product_name": "Pacote", "regular_price": "199.90", "sale_price": "149.90"}
            ])
            plans = get_plan_snapshot(("theme", "plugin"))
            packs = get_pack_snapshot()
            self.assertTrue(plans["cache"]["saved"])
            self.assertEqual(plans["by_kind"]["plugin"]["product_count"], 2)
            self.assertTrue(packs["cache"]["saved"])
            self.assertEqual(packs["products"][0]["product_id"], 7)


if __name__ == "__main__":
    unittest.main()
