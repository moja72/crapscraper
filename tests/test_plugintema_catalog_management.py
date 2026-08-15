from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import settings
from app.web import _build_comparison_sources_payload


class PluginTemaCatalogManagementTests(unittest.TestCase):
    def test_generated_catalog_exposes_total_and_kind_counts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "COMPARISON_IMPORTS_DIR", Path(tmp)
        ):
            path = Path(tmp) / "plugintema-custom-todos-20260813-201300-000001.csv"
            path.write_text(
                "ID,Tipo,Nome,Slug,URL,Status,Metadado: pt_versao,Metadado: site_oficial,Categorias\n"
                "1,simple,A,a,,publish,1,,Plugins\n"
                "2,simple,B,b,,publish,1,,Temas\n"
                "3,simple,C,c,,publish,1,,Templates\n",
                encoding="utf-8",
            )
            item = _build_comparison_sources_payload()["imported_catalogs"][0]
            self.assertEqual(item["items_count"], 3)
            self.assertEqual(item["plugin_count"], 1)
            self.assertEqual(item["theme_count"], 1)
            self.assertEqual(item["template_count"], 1)
            self.assertIn("(3 itens)", item["label"])


if __name__ == "__main__":
    unittest.main()
