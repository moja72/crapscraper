from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import app.addition_simple_creation_policy as policy


class FakeWoo:
    def list_product_categories(self, *, page: int = 1, per_page: int = 100):
        if page > 1:
            return []
        return [
            {"id": 10, "name": "Plugin", "parent": 0},
            {"id": 20, "name": "Temas", "parent": 0},
            {"id": 30, "name": "Saúde", "parent": 20},
        ]


class AdditionSimpleCreationPolicyTests(unittest.TestCase):
    def job(self, kind: str = "plugin") -> dict[str, str]:
        return {
            "job_id": "add-test",
            "kind": kind,
            "source_name": "Produto Teste",
            "source_version": "1.2.3",
            "source_product_url": "https://example.com/produto",
            "source_official_url": "https://example.com/oficial",
        }

    def test_description_prompt_requests_only_short_description(self) -> None:
        prompt = policy._description_prompt(self.job("theme"))
        self.assertIn("SOMENTE a breve descrição", prompt)
        self.assertIn("400 a 500 caracteres", prompt)
        self.assertIn("Crie páginas profissionais com total liberdade visual", prompt)
        self.assertNotIn("TÍTULO SEO:", prompt)
        self.assertNotIn("META DESCRIPTION:", prompt)
        self.assertNotIn("TAGS:", prompt)
        self.assertNotIn("CATEGORIA:", prompt)

    def test_clean_description_removes_label_and_markdown(self) -> None:
        raw = "**Breve descrição:** Uma descrição simples e objetiva para o produto."
        self.assertEqual(
            policy._clean_description(raw),
            "Uma descrição simples e objetiva para o produto.",
        )

    def test_missing_visual_reference_builds_attachment_free_prompt(self) -> None:
        missing = Path("missing/exemplo tema.webp")
        job = self.job("theme")

        with patch.object(policy.creative, "_reference_path", return_value=missing), \
             patch.object(policy.creative, "_attach_reference", return_value=False):
            reference, attached, prompt = policy._prepare_image_request(object(), job, "add-test")

        self.assertEqual(reference, missing)
        self.assertFalse(attached)
        self.assertIn("não há mockup local anexado", prompt.lower())
        self.assertNotIn("referência visual obrigatória", prompt.lower())
        self.assertNotIn("use o arquivo anexado", prompt.lower())

    def test_root_category_is_only_plugin_or_theme_root(self) -> None:
        self.assertEqual(policy._root_category(FakeWoo(), "plugin"), (10, "Plugin"))
        self.assertEqual(policy._root_category(FakeWoo(), "theme"), (20, "Temas"))

    def test_minimal_product_payload_has_only_root_category(self) -> None:
        job = {
            **self.job("theme"),
            "title": "Produto Teste",
            "short_description": "Descrição " * 40,
            "image_path": __file__,
            "woo_product_id": 0,
            "media_id": 123,
        }
        captured: dict[str, object] = {}

        class Woo(FakeWoo):
            def get_product_fresh(self, product_id: int):
                return {"id": product_id, "categories": [{"id": 20, "name": "Temas"}]}

        def fake_request(_woo, method: str, path: str, payload):
            captured["method"] = method
            captured["path"] = path
            captured["payload"] = payload
            return {"id": 456}

        with patch.object(policy.additions, "_row", return_value=job), \
             patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=Woo()), \
             patch.object(policy.additions, "_duplicate_product", return_value=None), \
             patch.object(policy.additions, "_wc_request", side_effect=fake_request), \
             patch.object(policy.additions, "_update", side_effect=lambda _job_id, **values: {**job, **values}):
            result = policy._create_minimal_product("add-test")

        payload = captured["payload"]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["categories"], [{"id": 20}])
        self.assertNotIn("tags", payload)
        self.assertNotIn("regular_price", payload)
        self.assertNotIn("attributes", payload)
        self.assertEqual(result["woo_product_id"], 456)


if __name__ == "__main__":
    unittest.main()
