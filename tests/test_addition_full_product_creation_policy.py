from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_full_product_creation_policy as policy


class _Woo:
    def __init__(self, *, version="1.5.2", status="draft", product_type="variable", variations=None):
        self.product = {
            "id": 103953,
            "status": status,
            "type": product_type,
            "categories": [{"id": 77, "name": "Tema"}],
            "meta_data": [{"key": "pt_versao", "value": version}],
        }
        self.variations = variations or [
            {
                "id": 1,
                "name": "Anual",
                "attributes": [{"name": "Plano", "option": "Anual"}],
                "regular_price": "33.90",
                "sale_price": "19.90",
                "downloadable": True,
                "virtual": True,
                "downloads": [{"name": "produto-1-5-2.zip", "file": "https://plugintema.com.br/downloads/produto-1-5-2.zip"}],
            },
            {
                "id": 2,
                "name": "Vitalício",
                "attributes": [{"name": "Plano", "option": "Vitalício"}],
                "regular_price": "39.80",
                "sale_price": "24.90",
                "downloadable": True,
                "virtual": True,
                "downloads": [{"name": "produto-1-5-2.zip", "file": "https://plugintema.com.br/downloads/produto-1-5-2.zip"}],
            },
        ]

    def get_product_fresh(self, product_id):
        return self.product

    def list_variations_fresh(self, product_id, per_page=100):
        return self.variations


class AdditionFullProductCreationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            "job_id": "add-test",
            "woo_product_id": 103953,
            "kind": "theme",
            "source_version": "1.5.2",
            "annual_regular": "33.90",
            "annual_sale": "19.90",
            "lifetime_regular": "39.80",
            "lifetime_sale": "24.90",
            "remote_file_name": "produto-1-5-2.zip",
            "remote_file_path": "https://plugintema.com.br/downloads/produto-1-5-2.zip",
        }

    def _validate(self, woo):
        with patch.object(policy.additions, "_row", return_value=dict(self.job)), \
             patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=woo), \
             patch.object(policy.simple, "_root_category", return_value=(77, "Tema")), \
             patch.object(policy.one_click, "_emit"):
            return policy._validate_store_product("add-test", expected_status="draft", progress=93)

    def test_accepts_complete_variable_product(self):
        product, variations = self._validate(_Woo())
        self.assertEqual(product["type"], "variable")
        self.assertEqual(len(variations), 2)

    def test_rejects_wrong_pt_versao(self):
        with self.assertRaisesRegex(RuntimeError, "pt_versao"):
            self._validate(_Woo(version="1.5.1"))

    def test_rejects_missing_variation(self):
        woo = _Woo()
        woo.variations = woo.variations[:1]
        with self.assertRaisesRegex(RuntimeError, "exatamente duas variações"):
            self._validate(woo)

    def test_rejects_download_not_bound_to_zip(self):
        woo = _Woo()
        woo.variations[0]["downloads"][0]["file"] = "https://example.test/outro.zip"
        with self.assertRaisesRegex(RuntimeError, "ZIP remoto esperado"):
            self._validate(woo)

    def test_rejects_wrong_variation_price(self):
        woo = _Woo()
        woo.variations[1]["sale_price"] = "20.00"
        with self.assertRaisesRegex(RuntimeError, "preços da variação Vitalício"):
            self._validate(woo)

    def test_price_normalization_accepts_comma(self):
        self.assertEqual(policy._price("R$ 39,80"), "39.80")


if __name__ == "__main__":
    unittest.main()
