from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
STANDARDIZER = (ROOT / "app" / "static" / "js" / "catalog-modal-standardization.js").read_text(encoding="utf-8")


class CatalogModalRuntimeStandardizationTests(unittest.TestCase):
    def test_runtime_module_is_loaded_before_catalog_management_capture_handler(self) -> None:
        standardizer_import = 'import "./catalog-modal-standardization.js";'
        catalog_management_import = 'import "./catalog-management.js";'
        self.assertIn(standardizer_import, APP)
        self.assertIn(catalog_management_import, APP)
        self.assertLess(APP.index(standardizer_import), APP.index(catalog_management_import))

    def test_visualize_labels_page_size_and_highlight_contract(self) -> None:
        for token in (
            'const DEFAULT_PAGE_SIZE="5"',
            'option.value=DEFAULT_PAGE_SIZE',
            'select.value=DEFAULT_PAGE_SIZE',
            'select.dispatchEvent(new Event("change",{bubbles:true}))',
            'button.textContent="Visualizar"',
            'data-catalog-preview',
            'data-catalog-view',
            'classList.toggle("is-previewing"',
            'border-color:var(--accent)!important',
        ):
            self.assertIn(token, STANDARDIZER)


if __name__ == "__main__":
    unittest.main()
