from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGINATION = (ROOT / "app" / "static" / "pagination_autojump.js").read_text(encoding="utf-8")


class CatalogModalListingContractTests(unittest.TestCase):
    def test_catalog_modals_share_visualize_and_search_contract(self) -> None:
        for token in (
            'normalize(button.textContent) !== "Visualizar"',
            'button.textContent = "Visualizar"',
            '"catalogos_preview_search", "Nome, versão, categoria ou link"',
            '"plugintema_manage_search", "Nome, ID, versão ou categoria"',
            'label.textContent = "Buscar no catálogo"',
            'title.textContent = "Catálogos PluginTema"',
            '[data-catalog-action="select"]',
            'scrollIntoView?.({ behavior: "smooth", block: "start" })',
        ):
            self.assertIn(token, PAGINATION)

    def test_catalog_modal_page_size_defaults_to_five_and_remains_editable(self) -> None:
        self.assertIn("const DEFAULT_PAGE_SIZE = 5", PAGINATION)
        for input_id in (
            "catalogos_page_size",
            "catalog_preview_page_size",
            "plugintema_manage_page_size",
        ):
            self.assertIn(f'"{input_id}"', PAGINATION)
        self.assertIn("catalogModalDefaultsApplied", PAGINATION)
        self.assertIn('input.value = String(DEFAULT_PAGE_SIZE)', PAGINATION)
        self.assertIn('input.dispatchEvent(new Event("change", { bubbles: true }))', PAGINATION)
        self.assertIn("parsed > 0 ? Math.min(parsed, 10000)", PAGINATION)


if __name__ == "__main__":
    unittest.main()
