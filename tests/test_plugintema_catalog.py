from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import comparison, comparison_decisions, settings
from app.web import _build_comparison_sources_payload, _generate_plugintema_comparison_catalog
from app.plugintema_catalog import (
    CATALOG_COLUMNS,
    CatalogFilters,
    build_catalog_rows,
    build_filtered_catalog_rows,
    encode_catalog_csv,
    read_all_products,
)


class PluginTemaCatalogExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.products = [
            {
                "id": 10,
                "type": "simple",
                "name": "Plugin A",
                "permalink": "https://plugintema.com.br/produto/plugin-a/",
                "categories": [{"name": "Plugins WordPress"}],
                "meta_data": [
                    {"key": "pt_versao", "value": "1.2.3"},
                    {"key": "site_oficial", "value": "https://plugin.test"},
                ],
            },
            {
                "id": 20,
                "type": "variable",
                "name": "Tema B",
                "categories": [{"name": "Temas"}],
                "meta_data": [{"key": "pt_versao", "value": "4.5.6"}],
            },
        ]

    def test_export_reuses_comparison_woocommerce_columns(self) -> None:
        rows = build_catalog_rows(self.products, kind="plugin")
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), CATALOG_COLUMNS)
        decoded = encode_catalog_csv(rows).decode("utf-8-sig")
        parsed = list(csv.DictReader(io.StringIO(decoded)))
        self.assertEqual(parsed[0]["ID"], "10")
        self.assertEqual(parsed[0]["Metadado: pt_versao"], "1.2.3")
        normalized = comparison._normalize_site_rows(parsed)
        self.assertEqual(normalized[0]["site_product_key"], "site:id:10")
        self.assertEqual(normalized[0]["site_version"], "1.2.3")
        self.assertEqual(normalized[0]["site_product_url"], "https://plugintema.com.br/produto/plugin-a/")

    def test_plugins_and_themes_are_filtered_by_existing_categories(self) -> None:
        self.assertEqual([row["ID"] for row in build_catalog_rows(self.products, kind="plugin")], ["10"])
        self.assertEqual([row["ID"] for row in build_catalog_rows(self.products, kind="theme")], ["20"])

    def test_brand_category_containing_themes_does_not_change_plugin_kind(self) -> None:
        product = {
            "id": 30,
            "name": "Thrive Architect Plugin",
            "categories": [{"name": "Plugin"}, {"name": "Thrive Themes"}],
        }
        self.assertEqual([row["ID"] for row in build_catalog_rows([product], kind="plugin")], ["30"])
        self.assertEqual(build_catalog_rows([product], kind="theme"), [])

    def test_product_pagination_is_read_only_and_complete(self) -> None:
        class Woo:
            def __init__(self) -> None:
                self.calls = []

            def list_products(self, **kwargs):
                self.calls.append(kwargs)
                return [{"id": kwargs["page"]}] if kwargs["page"] == 1 else []

        woo = Woo()
        self.assertEqual(read_all_products(woo, per_page=1), [{"id": 1}])
        self.assertEqual(woo.calls, [
            {"page": 1, "per_page": 1, "status": "publish"},
            {"page": 2, "per_page": 1, "status": "publish"},
        ])

    def test_custom_filters_type_category_status_query_ids_and_version(self) -> None:
        products = self.products + [{
            "id": 30, "name": "Plugin sem versao", "slug": "plugin-sem-versao",
            "status": "draft", "categories": [{"name": "Plugins WordPress"}], "meta_data": [],
        }]
        rows = build_filtered_catalog_rows(products, CatalogFilters(
            kinds=("plugin", "theme"), categories=("Plugins WordPress",),
            statuses=("draft",), query="sem versao", product_ids=(30,), version="without",
        ))
        self.assertEqual([row["ID"] for row in rows], ["30"])
        self.assertEqual(tuple(rows[0]), CATALOG_COLUMNS)

    def test_quick_presets_keep_plugins_and_themes_separate(self) -> None:
        plugins = build_filtered_catalog_rows(self.products, CatalogFilters(kinds=("plugin",)))
        themes = build_filtered_catalog_rows(self.products, CatalogFilters(kinds=("theme",)))
        self.assertEqual([row["ID"] for row in plugins], ["10"])
        self.assertEqual([row["ID"] for row in themes], ["20"])

    def test_custom_catalog_supports_reserved_templates_and_a_safe_name(self) -> None:
        products = self.products + [{
            "id": 40, "type": "simple", "name": "Template futuro",
            "status": "publish", "categories": [{"name": "Templates"}], "meta_data": [],
        }]

        class Woo:
            def list_products(self, **_kwargs):
                return products

        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "COMPARISON_IMPORTS_DIR", Path(directory)
        ):
            generated = _generate_plugintema_comparison_catalog({
                "mode": "custom", "kind": "all", "catalog_name": "Minha base / segura",
            }, Woo())
            self.assertNotIn("/", generated["filename"])
            with (Path(directory) / generated["filename"]).open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["ID"] for row in rows}, {"10", "20", "40"})

    def test_multiple_presets_and_name_work_without_custom_mode(self) -> None:
        products = self.products + [{
            "id": 40, "type": "simple", "name": "Template futuro",
            "status": "publish", "categories": [{"name": "Templates"}], "meta_data": [],
        }]

        class Woo:
            def list_products(self, **_kwargs):
                return products

        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "COMPARISON_IMPORTS_DIR", Path(directory)
        ):
            generated = _generate_plugintema_comparison_catalog({
                "mode": "selection", "kinds": ["plugin", "template"],
                "catalog_name": "Plugins e templates escolhidos",
            }, Woo())
            self.assertIn("Plugins_e_templates_escolhidos", generated["filename"])
            with (Path(directory) / generated["filename"]).open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["ID"] for row in rows}, {"10", "40"})

    def test_generated_catalog_is_atomic_visible_and_previous_survives_error(self) -> None:
        class Woo:
            def list_products(self, **_kwargs):
                return self.products

        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "COMPARISON_IMPORTS_DIR", Path(directory)
        ):
            woo = Woo()
            woo.products = self.products
            generated = _generate_plugintema_comparison_catalog({"mode": "plugin"}, woo)
            self.assertTrue((Path(directory) / generated["filename"]).is_file())
            sources = _build_comparison_sources_payload()["imported_catalogs"]
            self.assertTrue(any(item["id"] == generated["catalog_id"] for item in sources))
            existing = (Path(directory) / generated["filename"]).read_bytes()
            woo.list_products = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("API indisponivel"))
            with self.assertRaises(RuntimeError):
                _generate_plugintema_comparison_catalog({"mode": "theme"}, woo)
            self.assertEqual((Path(directory) / generated["filename"]).read_bytes(), existing)

    def test_generation_uses_only_read_methods(self) -> None:
        class Woo:
            def __init__(self): self.calls = []
            def list_products(self, **kwargs):
                self.calls.append(("GET", kwargs))
                return []
            def write(self, *_args, **_kwargs):
                raise AssertionError("write não pode ser chamado")
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "COMPARISON_IMPORTS_DIR", Path(directory)
        ):
            woo = Woo()
            _generate_plugintema_comparison_catalog({"mode": "plugin"}, woo)
            self.assertTrue(woo.calls)
            self.assertTrue(all(method == "GET" for method, _payload in woo.calls))


class PersistentRelationshipRegressionTests(unittest.TestCase):
    def test_manual_relationship_is_reused_by_a_future_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "decisions.sqlite3"
            source = root / "source.csv"
            site = root / "site.csv"
            source.write_text(
                "nome_produto,versao_produto,link_produto,pagina_oficial,categoria_nome\n"
                "Nome sem correspondência,2.0,https://source.test/item,,Temas\n",
                encoding="utf-8",
            )
            site.write_text(
                "ID,Tipo,Nome,Metadado: pt_versao,Metadado: site_oficial,Categorias\n"
                "94567,simple,Outro nome,1.0,,Temas\n",
                encoding="utf-8",
            )
            source_key = "source:product_url:source.test/item"
            with patch.object(settings, "COMPARISON_DECISIONS_DB_PATH", database):
                comparison_decisions.save_relationship(
                    "site:id:94567", source_key, "manual_confirmed"
                )
                first = comparison._build_full_comparison(source, site)
                second = comparison._build_full_comparison(source, site)
            for payload in (first, second):
                row = payload["rows"][0]
                self.assertEqual(row["match_method"], "manual_confirmed")
                self.assertEqual(row["source_product_key"], source_key)


class CollectionUiContractTests(unittest.TestCase):
    def test_navigation_modal_queue_and_results_controls_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn('id="tab_btn_principal">Coletar</button>', web)
        self.assertIn("Comparar", web)
        self.assertIn("Atualizar", web)
        self.assertIn("Adicionar", web)
        self.assertNotIn('id="tab_btn_catalogos"', web)
        self.assertNotIn('id="tab_btn_fila"', web)
        self.assertIn("openCatalogosModal", js)
        self.assertIn("collect-queue-accordion", js)
        self.assertIn("collect-runs-accordion", js)
        self.assertIn('window.localStorage.getItem("runs_manager_expanded") === "1"', js)
        self.assertIn("collection_operations_group", web + js)
        self.assertIn("catalog_management_card", web + js)
        self.assertNotIn("Exportação da PluginTema", js)
        self.assertNotIn("plugintema_export_kind", js)
        self.assertIn('close.textContent = "×"', js)
        self.assertNotIn('close.textContent = "Fechar"', js)
        self.assertNotIn('controls.className = "comparison-results-controls"', js)
        self.assertIn('results.insertBefore(filters, bulk)', js)
        self.assertIn('results.insertBefore(actions, bulk)', js)
        self.assertIn("plugintemaCatalogExport", js)

    def test_comparison_can_select_current_page_or_whole_filtered_result(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn('id="comparison_select_page"', web)
        self.assertIn('type="checkbox" id="comparison_select_all_results"', web)
        self.assertIn('id="comparison_clear_selection"', web)
        self.assertIn("async function setAllComparisonResultsSelected(checked)", js)
        self.assertIn('byId("comparison_select_all_results")?.addEventListener("change"', js)
        self.assertIn("UI.comparison.allResultsSelected = false", js)
        self.assertIn("comparisonFilterSnapshot()", js)
        self.assertIn('page_size: "1000"', js)
        self.assertIn("selectedItemIds: new Set()", js)
        self.assertIn("selectedRowsById", js)

    def test_comparison_results_reuses_listing_pagination_pattern(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        css = (root / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        results = web.split('id="comparison_results_card"', 1)[1].split('id="plugintema_update_modal"', 1)[0]
        self.assertIn('class="listing-meta-row comparison-listing-meta"', results)
        self.assertIn('class="listing-pagination comparison-pagination"', results)
        self.assertIn('id="comparison_result_meta"', results)
        self.assertIn('id="comparison_page_size"', results)
        self.assertIn('id="comparison_prev_btn">← Anterior', results)
        self.assertIn('id="comparison_next_btn">Próxima →', results)
        self.assertLess(results.index('id="comparison_page_size"'), results.index('class="comparison-table-wrap"'))
        self.assertEqual(web.count('id="comparison_page_size"'), 1)
        self.assertEqual(web.count('id="comparison_prev_btn"'), 1)
        self.assertIn('class="listing-meta-row"', js)
        self.assertIn('class="listing-pagination"', js)
        self.assertIn(".listing-pagination > button", css)

    def test_comparison_can_generate_and_select_plugintema_catalog(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn('id="comparison_update_plugintema_btn"', web)
        self.assertIn('id="plugintema_update_modal"', web)
        self.assertIn('type="checkbox" name="plugintema_preset_kind" value="plugin" checked', web)
        self.assertIn('type="checkbox" name="plugintema_preset_kind" value="theme"', web)
        self.assertIn('type="checkbox" name="plugintema_preset_kind" value="template"', web)
        self.assertIn('type="radio" name="plugintema_custom_mode" value="custom"', web)
        self.assertIn("openPluginTemaUpdateModal", js)
        self.assertIn("closePluginTemaUpdateModal", js)
        self.assertIn("preferredTarget: result.catalog_id", js)
        self.assertIn("plugintema_product_search_btn", web + js)
        self.assertIn("plugintemaSelectedProducts", js)
        self.assertIn("Encadeamento simultâneo entre catálogos e contextos", js)
        self.assertIn('id="updates_copy_log"', web)
        self.assertIn('id="comparison_manage_plugintema_btn"', web)
        self.assertIn('id="plugintema_manage_modal"', web)
        self.assertIn('id="plugintema_manage_prev"', web)
        self.assertIn('id="plugintema_manage_next"', web)
        self.assertIn('id="plugintema_manage_type"', web)
        self.assertIn('id="plugintema_manage_status"', web)
        self.assertIn('id="plugintema_custom_name"', web)
        self.assertIn('<option value="template">Templates</option>', web)
        self.assertIn('<option value="all">Plugins, Temas e Templates</option>', web)
        self.assertIn("UI.plugintemaManagePageSize", js)
        self.assertIn('id="plugintema_manage_page_size"', web)
        self.assertIn('id="plugintema_manage_range"', web)
        self.assertIn('id="plugintema_manage_download"', web)
        self.assertIn('class="catalogos-table plugintema-manage-table"', web)
        self.assertIn('"plugintemaCatalogDownload": "/plugintema/catalogo/baixar"', web)
        self.assertIn("downloadPluginTemaManagedCatalog", js)
        manager = web.split('id="plugintema_manage_modal"', 1)[1].split('id="tab_panel_atualizacoes"', 1)[0]
        self.assertLess(manager.index('id="plugintema_manage_search"'), manager.index('id="plugintema_manage_range"'))
        self.assertLess(manager.index('id="plugintema_manage_range"'), manager.index('id="plugintema_manage_prev"'))
        self.assertLess(manager.index('id="plugintema_manage_prev"'), manager.index('id="plugintema_manage_rows"'))
        self.assertIn('pluginTemaCatalogs = importedCatalogs.filter', js)
        self.assertIn("Contextos dos catálogos", web)
        self.assertIn('id="catalogos_preview_copy_log_btn"', web)
        self.assertIn('preview.kind !== "log"', js)
        self.assertIn("deletePluginTemaManagedCatalog", js)
        self.assertIn("atualizados em", web)
        self.assertNotIn("Filtrar por catálogo", web)
        self.assertIn("Execuções Simultâneas", js)
        self.assertNotIn("generatePluginTemaComparisonCatalog();\n    await refreshComparison", js)

    def test_collection_context_switch_preserves_active_run_options(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(js.count("const activeRunOptions = readRunOptionsFromForm();"), 3)
        self.assertGreaterEqual(js.count("postJson(UI.endpoints.config, activeRunOptions)"), 3)
        self.assertIn(".collect-runs-accordion .runs-manager-header>span:first-child", (root / "app" / "static" / "panel.css").read_text(encoding="utf-8"))

    def test_collection_operational_controls_are_clear_and_scoped(self) -> None:
        root = Path(__file__).resolve().parents[1]
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        css = (root / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        self.assertIn('id="create_and_start_run_btn"', js)
        self.assertIn("async function createAndStartRun()", js)
        self.assertIn('postJson(startEndpoint, {', js)
        activate = js.split("function activateMainTab(tabKey)", 1)[1].split("function setCatalogPreviewPage", 1)[0]
        self.assertIn('.page-head-sticky")?.classList.toggle("hidden", normalized !== "principal")', activate)
        self.assertEqual(js.count('.page-head-sticky")?.classList.toggle("hidden", normalized !== "principal")'), 1)
        self.assertIn('document.body.dataset.activeTab = normalized', activate)
        self.assertIn('body:not([data-active-tab="principal"]) .page-head-sticky', css)
        self.assertIn('<div class="log-copy-row">\n          <button class="btn-success" id="copy_logs_btn"', (root / "app" / "web.py").read_text(encoding="utf-8"))
        self.assertIn('class="btn-danger btn-sm" type="button" data-fila-action="remove">Apagar', js)
        self.assertIn("border-radius: 50%", css)
        self.assertIn(".log-copy-row .btn-success{flex:0 0 auto!important;width:auto!important", css)
        self.assertIn('window.localStorage.getItem("runs_manager_expanded") === "1"', js)
        self.assertIn(".run-remove-btn{box-sizing:border-box!important;display:inline-grid!important", css)

    def test_visible_update_states_relationships_and_collection_help_are_localized(self) -> None:
        root = Path(__file__).resolve().parents[1]
        web = (root / "app" / "web.py").read_text(encoding="utf-8")
        js = (root / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertNotIn("Run started at", web)
        self.assertNotIn("Run finished at", web)
        for label in ("Aprovado", "Plano pronto", "Rollback necessário", "Rollback concluído", "Interrompido"):
            self.assertIn(label, web + js)
        for label in ("Vinculação automática", "Vinculação manual confirmada"):
            self.assertIn(label, web + js)
        self.assertIn("UPDATE_STATUS_LABELS", js)
        self.assertIn("UPDATE_RELATIONSHIP_LABELS", js)
        for field in (
            "Resumo", "Fila de continuação", "Fase atual", "Categoria atual",
            "Item atual", "Última atualização", "Início da execução", "Fim da execução",
        ):
            self.assertIn(f'aria-label="Ajuda sobre {field}"', web)


if __name__ == "__main__":
    unittest.main()
