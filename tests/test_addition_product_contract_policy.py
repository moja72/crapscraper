from __future__ import annotations

import unittest

import app.addition_product_contract_policy as policy


class _FakeWoo:
    def get(self, path, params=None):
        if path.endswith("/products/attributes"):
            return [{"id": 12, "name": "Licença", "slug": "pa_licenca"}]
        if path.endswith("/products/attributes/12/terms"):
            return [
                {"id": 798, "name": "1 ano", "slug": "1-ano"},
                {"id": 799, "name": "vitalício", "slug": "vitalicio"},
            ]
        return []


class AdditionProductContractPolicyTests(unittest.TestCase):
    def setUp(self):
        self.plugin = {"source_name": "3D Carousel For WordPress", "kind": "plugin"}
        self.theme = {"source_name": "Example Theme", "kind": "theme"}

    def test_description_prompt_is_short_and_has_no_internal_code(self):
        prompt = policy._short_description_prompt(self.plugin)
        self.assertNotIn("CSADD", prompt)
        self.assertNotIn("IDENTIFICADOR INTERNO", prompt)
        self.assertNotIn("TÍTULO SEO", prompt)
        self.assertLess(len(prompt), 1200)
        self.assertIn("Responda SOMENTE com o parágrafo final", prompt)

    def test_plugin_image_prompt_is_short_and_requires_new_image(self):
        prompt = policy._short_image_prompt(self.plugin)
        self.assertNotIn("CSADD", prompt)
        self.assertNotIn("IDENTIFICADOR INTERNO", prompt)
        self.assertLess(len(prompt), 1200)
        self.assertIn("NOVA imagem", prompt)
        self.assertIn("Vitalício | Ilimitado | Atualizado", prompt)
        self.assertIn("não reutilize", prompt.lower())

    def test_theme_image_prompt_uses_theme_mockup_rules(self):
        prompt = policy._short_image_prompt(self.theme)
        self.assertIn("monitor Apple", prompt)
        self.assertIn("celular", prompt)
        self.assertIn("NOVA imagem", prompt)

    def test_license_contract_uses_required_taxonomy_terms(self):
        contract = policy._license_contract(_FakeWoo())
        self.assertEqual(contract["attribute_id"], 12)
        self.assertEqual(contract["annual"]["id"], 798)
        self.assertEqual(contract["annual"]["slug"], "1-ano")
        self.assertEqual(contract["lifetime"]["id"], 799)
        self.assertEqual(contract["lifetime"]["slug"], "vitalicio")

    def test_product_license_attribute_accepts_exact_options(self):
        product = {
            "attributes": [{
                "id": 12,
                "name": "Licença",
                "slug": "pa_licenca",
                "variation": True,
                "options": ["1 ano", "vitalício"],
            }]
        }
        self.assertTrue(policy._has_license_attribute(product))


if __name__ == "__main__":
    unittest.main()
