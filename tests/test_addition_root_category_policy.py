from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import app.addition_root_category_policy as policy


class AdditionRootCategoryPolicyTests(unittest.TestCase):
    def test_theme_job_persists_tema_before_creation(self) -> None:
        woo = object()
        with patch.object(policy, "_ensure_category_column"), \
             patch.object(policy.additions, "_row", return_value={"kind": "theme"}), \
             patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=woo), \
             patch.object(policy.simple, "_root_category", return_value=(123, "Tema")) as root, \
             patch.object(policy.additions, "_update", return_value={"kind": "theme", "category_name": "Tema"}) as update, \
             patch.object(policy.one_click, "_emit"):
            result = policy._prepare_root_category("job-theme")

        root.assert_called_once_with(woo, "theme")
        update.assert_called_once_with("job-theme", category_name="Tema", error="")
        self.assertEqual(result["category_name"], "Tema")

    def test_plugin_job_persists_plugin_before_creation(self) -> None:
        woo = object()
        with patch.object(policy, "_ensure_category_column"), \
             patch.object(policy.additions, "_row", return_value={"kind": "plugin"}), \
             patch.object(policy.additions.web, "_build_store_woocommerce_client", return_value=woo), \
             patch.object(policy.simple, "_root_category", return_value=(456, "Plugin")) as root, \
             patch.object(policy.additions, "_update", return_value={"kind": "plugin", "category_name": "Plugin"}) as update, \
             patch.object(policy.one_click, "_emit"):
            result = policy._prepare_root_category("job-plugin")

        root.assert_called_once_with(woo, "plugin")
        update.assert_called_once_with("job-plugin", category_name="Plugin", error="")
        self.assertEqual(result["category_name"], "Plugin")

    def test_wrapper_prepares_category_before_base_create(self) -> None:
        calls: list[str] = []

        def prepare(job_id: str):
            calls.append(f"prepare:{job_id}")
            return {}

        def base(job_id: str, confirmation: str):
            calls.append(f"create:{job_id}:{confirmation}")
            return {"ok": True}

        with patch.object(policy, "_prepare_root_category", side_effect=prepare), \
             patch.object(policy, "_ORIGINAL_CREATE_OR_RESUME_DRAFT", base):
            result = policy._create_or_resume_draft_with_root_category("job-1", "CRIAR RASCUNHO")

        self.assertEqual(
            calls,
            ["prepare:job-1", "create:job-1:CRIAR RASCUNHO"],
        )
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
