from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import settings, storage
from app.app import ScraperApp
from app.web import _build_catalogs_payload


class CatalogManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(settings, "DATA_DIR", root / "data"),
            patch.object(settings, "LOGS_DIR", root / "logs"),
            patch.object(settings, "SLOTS_DIR", root / "data" / "slots"),
            patch.object(settings, "SLOTS_META_JSON_PATH", root / "data" / "slots_meta.json"),
        ]
        for item in self.patches:
            item.start()
        storage.save_slots_meta({"slots": ["default", "tema"], "default_slot": "default", "active_slot": "default"})

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _context(self, slot: str, item_type: str, items: list[dict] | None = None) -> Path:
        path = storage.get_context_dir(
            site_key=settings.DEFAULT_SITE_KEY,
            item_type_key=item_type,
            account_key=settings.DEFAULT_ACCOUNT_KEY,
            slot_name=slot,
            ensure=True,
        )
        storage.save_catalog_items(
            items or [],
            site_key=settings.DEFAULT_SITE_KEY,
            item_type_key=item_type,
            account_key=settings.DEFAULT_ACCOUNT_KEY,
            slot_name=slot,
        )
        return path

    def test_remove_context_persists_and_updates_catalog_count(self) -> None:
        removed = self._context("tema", "theme", [{"nome_produto": "A", "link_produto": "https://test/A"}])
        self._context("tema", "plugin", [{"nome_produto": "B", "link_produto": "https://test/B"}])
        before = [row for row in _build_catalogs_payload()["catalogos"] if row["slot_name"] == "tema"]
        ok, _message = storage.remove_slot_context("tema", settings.DEFAULT_SITE_KEY, "theme", settings.DEFAULT_ACCOUNT_KEY)
        after = [row for row in _build_catalogs_payload()["catalogos"] if row["slot_name"] == "tema"]
        self.assertTrue(ok)
        self.assertFalse(removed.exists())
        self.assertEqual(len(before), 2)
        self.assertEqual(len(after), 1)
        self.assertFalse(removed.exists(), "o contexto não pode reaparecer após nova leitura/restart")

    def test_delete_catalog_removes_only_known_slot_and_all_contexts(self) -> None:
        self._context("tema", "theme", [{"nome_produto": "A", "link_produto": "https://test/A"}])
        untouched = self._context("default", "plugin", [{"nome_produto": "B", "link_produto": "https://test/B"}])
        ok, _message = storage.delete_slot("tema")
        self.assertTrue(ok)
        self.assertFalse((settings.SLOTS_DIR / "tema").exists())
        self.assertTrue(untouched.exists())
        self.assertNotIn("tema", storage.load_slots_meta()["slots"])
        for invalid in ("../tema", "tema/../../default", "TEMA"):
            ok, _message = storage.delete_slot(invalid)
            self.assertFalse(ok)

    def test_remove_zero_contexts_keeps_nonempty_context(self) -> None:
        zero = self._context("tema", "theme", [])
        kept = self._context("tema", "plugin", [{"nome_produto": "B", "link_produto": "https://test/B"}])
        app = ScraperApp(
            site_key=settings.DEFAULT_SITE_KEY,
            item_type_key="plugin",
            account_key=settings.DEFAULT_ACCOUNT_KEY,
            slot_name="tema",
            auto_load_summary=False,
        )
        app.log = lambda *_args, **_kwargs: None
        result = app.remove_zero_item_contexts("tema")
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["removed"]), 1)
        self.assertFalse(zero.exists())
        self.assertTrue(kept.exists())

    def test_principal_catalog_cannot_be_renamed(self) -> None:
        success, message, resulting_name = storage.rename_slot("default", "novo-principal")
        self.assertFalse(success)
        self.assertIn("Principal", message)
        self.assertEqual(resulting_name, "default")
        self.assertIn("default", storage.load_slots_meta()["slots"])


class CatalogManagementUiContractTests(unittest.TestCase):
    def test_catalog_controls_and_queue_title_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn("Gerenciar Cat", web)
        self.assertIn('id="catalogos_remove_zero_btn"', web)
        self.assertIn("catalogo-delete-button", js)
        self.assertIn('class="btn-danger" id="slot_delete_btn"', web)
        self.assertIn("catalogo-clear-button", js)
        self.assertIn("catalogo-default-button", js)
        self.assertIn("clearCatalogo", js)
        self.assertIn("defineDefaultCatalogo", js)
        self.assertIn("loadCatalogo", js)
        self.assertIn("📂", js)
        self.assertIn("⭐", js)
        self.assertIn("🧹", js)
        self.assertIn("🗑️", js)
        self.assertIn('id="slot_default_btn"', web)
        self.assertNotIn('id="slot_default_checkbox"', web)
        self.assertIn('id="config_modal"', web)
        self.assertIn('id="open_config_modal_btn"', web)
        self.assertIn('<div class="section-title">Contexto</div>', web)
        self.assertIn('value="complete" selected', web)
        self.assertIn('id="save_every_items" type="number" min="1" step="1" value="10"', web)
        self.assertIn('id="save_every_minutes" type="number" min="1" step="1" value="10"', web)
        self.assertIn('classList.toggle("hidden", normalized !== "principal")', js)
        self.assertIn('class="log-copy-row"><button class="btn-success hidden" id="catalogos_preview_copy_log_btn"', web)
        self.assertIn('class="log-copy-row"><button class="btn-success" id="updates_copy_log"', web)
        self.assertIn("aria-label=\"Excluir catálogo", js)
        for token in ("catalogos_search", "catalogos_prev_page", "catalogos_next_page",
                      "catalogo-view-button", "showCatalogoContexts", "Data não registrada"):
            self.assertIn(token, web + js)
        self.assertIn("A validação normal confere os dados essenciais", web)
        self.assertIn("effectiveItemTypeKey", js)
        self.assertIn("itemTypes[0]?.key", js)
        self.assertIn("isAlreadyActive", js)
        self.assertIn('aria-pressed="${isContextFilterActive}"', js)
        self.assertIn("catalogo-context-line", js)
        self.assertIn("context.items_count", js)
        self.assertIn("context.updated_at", js)
        self.assertIn("catalogo-context-accordion", js)
        self.assertIn('entry.contexts.length === 1 ? "Contexto" : "Contextos"', js)
        self.assertNotIn('<summary><span>Contexto</span><span class="badge">', js)
        self.assertIn("catalogo-summary-meta", js)
        self.assertIn("updated_at_timestamp", web + js)
        self.assertIn("catalogo-availability-icon", js)
        self.assertIn('id="catalogos_loading" role="status"', web)
        self.assertIn('id="catalogos_content"', web)
        self.assertIn("setCatalogosLoading", js)
        self.assertIn("catalogo-rename-button", js)
        self.assertIn("openCatalogRenameModal", js)
        self.assertIn('id="catalog_rename_modal"', web)
        self.assertIn('old_slot_name: oldName', js)
        self.assertIn('isPrincipal ? ""', js)
        self.assertNotIn("📄 Catálogo disponível<br>", js)
        self.assertIn("fila-loading", js)
        self.assertIn("aria-busy", js)
        queue = web.split('id="tab_panel_fila"', 1)[1].split('id="tab_panel_comparacao"', 1)[0]
        self.assertNotIn('<div class="section-title">Fila</div>', queue)


if __name__ == "__main__":
    unittest.main()
