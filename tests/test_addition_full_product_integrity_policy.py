from __future__ import annotations

import unittest
from unittest.mock import patch

import app.addition_full_product_integrity_policy as policy


class _Woo:
    pass


class AdditionFullProductIntegrityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.product = {
            "id": 100,
            "short_description": (
                "Crie uma loja médica organizada com um tema preparado para apresentar serviços, produtos e informações de saúde. "
                "O 123 Medicine ajuda farmácias e clínicas a estruturar conteúdo comercial e institucional de forma clara. "
                "É indicado para projetos WordPress voltados ao setor médico e farmacêutico."
            ),
            "categories": [{"id": 77, "name": "Tema"}],
            "images": [{"id": 900}],
        }
        self.job = {"job_id": "add-test", "kind": "theme", "media_id": 900}

    def _validate(self, product=None, job=None):
        product = product or dict(self.product)
        job = job or dict(self.job)
        policy._ORIGINAL_VALIDATE = lambda *args, **kwargs: (product, [{"id": 1}, {"id": 2}])
        with patch.object(policy.additions, "_row", return_value=job), \
             patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=_Woo()), \
             patch.object(policy.simple, "_root_category", return_value=(77, "Tema")):
            return policy._strict_validate_store_product("add-test", expected_status="draft", progress=93)

    def test_accepts_exact_root_category_description_and_image(self):
        product, variations = self._validate()
        self.assertEqual(product["id"], 100)
        self.assertEqual(len(variations), 2)

    def test_rejects_extra_category(self):
        product = dict(self.product)
        product["categories"] = [{"id": 77}, {"id": 99}]
        with self.assertRaisesRegex(RuntimeError, "somente na categoria raiz"):
            self._validate(product=product)

    def test_rejects_missing_media_id(self):
        job = dict(self.job)
        job["media_id"] = 0
        with self.assertRaisesRegex(RuntimeError, "media_id"):
            self._validate(job=job)

    def test_rejects_image_not_attached(self):
        product = dict(self.product)
        product["images"] = [{"id": 901}]
        with self.assertRaisesRegex(RuntimeError, "imagem principal"):
            self._validate(product=product)

    def test_rejects_invalid_short_description(self):
        product = dict(self.product)
        product["short_description"] = "Curta demais."
        with self.assertRaisesRegex(RuntimeError, "breve descrição"):
            self._validate(product=product)


if __name__ == "__main__":
    unittest.main()
