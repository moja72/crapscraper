from __future__ import annotations

import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def comparison_row(item_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "comparison_item_id": item_id,
        "status": "updated",
        "status_label": "Atualizado",
        "status_reason": "Versões equivalentes.",
        "site_product_key": f"site:{item_id}",
        "site_id": item_id,
        "site_name": f"PluginTema {item_id}",
        "site_version": "2.13.3",
        "site_version_quality": "valid",
        "site_version_reason": "Versão válida.",
        "site_official_url": f"https://site.test/{item_id}",
        "site_categories": "Tema",
        "source_product_key": f"source:{item_id}",
        "source_name": f"Ultrapack {item_id}",
        "source_version": "2.14.2",
        "source_version_quality": "valid",
        "source_version_reason": "Versão válida.",
        "source_product_url": f"https://source.test/{item_id}",
        "source_official_url": f"https://official.test/{item_id}",
        "source_category": "Tema",
        "match_method": "normalized_name",
        "match_method_label": "Nome normalizado idêntico",
        "match_confidence": "high",
        "match_level_label": "Exata",
        "match_score": 100,
        "match_favorable_signals": ["Nome equivalente"],
        "match_conflicting_signals": [],
        "match_candidates": [],
        "decision": "pending",
        "decision_label": "Pendente",
        "recommended_action": "manual_review",
        "recommended_action_label": "Revisar manualmente.",
    }
    row.update(overrides)
    return row


class ComparisonBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            cls.playwright.stop()
            raise unittest.SkipTest(f"Chromium indisponível: {exc}") from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        self.page.set_content(
            """<!doctype html><html><head></head><body>
            <script id="monitor-boot-data" type="application/json">{}</script>
            <div id="comparison_summary_card" class="hidden"></div>
            <div id="comparison_results_card" class="hidden"></div>
            <span id="comparison_result_meta"></span><span id="comparison_page_label"></span>
            <button id="comparison_prev_btn"></button><button id="comparison_next_btn"></button>
            <input id="comparison_select_page" type="checkbox"><button id="comparison_bulk_apply_btn"></button>
            <table class="comparison-table"><tbody id="comparison_rows"></tbody></table>
            <div class="comparison-link-modal hidden" id="comparison_link_modal" role="dialog" aria-modal="true" aria-labelledby="comparison_link_modal_title" tabindex="-1">
              <div class="comparison-link-modal-backdrop"></div><div class="comparison-link-modal-card">
                <h2 id="comparison_link_modal_title">Vincular produto</h2>
                <div id="comparison_link_modal_product"></div><button id="comparison_link_modal_close">Fechar</button>
                <div id="comparison_link_modal_suggestions"></div><input id="comparison_link_modal_query">
                <button id="comparison_link_modal_search">Buscar</button><div id="comparison_link_modal_status"></div>
                <div id="comparison_link_modal_results"></div>
              </div>
            </div>
            <div class="comparison-link-modal comparison-diagnostic-modal hidden" id="comparison_diagnostic_modal" role="dialog" aria-modal="true" aria-labelledby="comparison_diagnostic_modal_title" tabindex="-1">
              <div class="comparison-link-modal-backdrop"></div><div class="comparison-link-modal-card">
                <h2 id="comparison_diagnostic_modal_title">Diagnóstico</h2>
                <div id="comparison_diagnostic_modal_subtitle"></div><button id="comparison_diagnostic_modal_close">Fechar</button>
                <div id="comparison_diagnostic_modal_content"></div>
              </div>
            </div></body></html>"""
        )
        self.page.add_style_tag(content=(ROOT / "app/static/panel.css").read_text(encoding="utf-8"))
        self.page.evaluate("window.__CRAPSCRAPER_COMPARISON_TEST__ = true")
        self.page.add_script_tag(content=(ROOT / "app/static/panel.js").read_text(encoding="utf-8"))
        self.page.evaluate("window.__comparisonUiTest.bindComparisonControls()")

    def tearDown(self) -> None:
        self.page.close()

    def render_representative_rows(self) -> None:
        candidate = comparison_row(
            "candidate",
            status="site_only",
            status_label="Somente PluginTema",
            source_product_key="",
            source_name="",
            source_version="",
            recommended_action_label="Revisar o candidato aproximado antes de decidir.",
            match_method="unmatched",
            match_method_label="Sem correspondência",
            match_confidence="none",
            match_level_label="Provável",
            match_score=88,
            match_candidates=[{
                "source_product_key": "source:candidate",
                "source_name": "Divi Extended | Divi Layouts Extended",
                "source_version": "3.16",
                "source_product_url": "https://source.test/candidate",
                "source_official_url": "https://official.test/candidate",
                "source_category": "Tema",
                "match_score": 88,
                "match_level_label": "Provável",
            }],
        )
        rows = [
            candidate,
            comparison_row("exact"),
            comparison_row("none", status="site_only", status_label="Somente PluginTema", source_product_key="", source_name="", source_version="", match_candidates=[]),
            comparison_row("plugin-only", source_product_key="", source_name="", source_version=""),
            comparison_row("ultrapack-only", site_product_key="", site_id="", site_name="", site_version=""),
            comparison_row("update", status="update_available", status_label="Atualização disponível", recommended_action_label="Revisar e aprovar atualização."),
            comparison_row("missing-version", site_version="", recommended_action_label="Conferir e cadastrar a versão no site."),
        ]
        self.page.evaluate(
            "rows => window.__comparisonUiTest.renderComparison({rows, summary: {}, pagination: {page: 1, page_size: 100, total_pages: 1, total_rows: rows.length}})",
            rows,
        )

    def test_semantic_columns_arrows_and_representative_payloads(self) -> None:
        self.render_representative_rows()
        rows = self.page.locator("#comparison_rows tr")
        self.assertEqual(rows.count(), 7)
        for index in range(rows.count()):
            self.assertEqual(rows.nth(index).locator(":scope > td").count(), 7)
            self.assertEqual(rows.nth(index).locator(".comparison-products-pair .comparison-pair-arrow").inner_text(), "→")
            self.assertEqual(rows.nth(index).locator(".comparison-versions .comparison-pair-arrow").inner_text(), "→")

        candidate_cells = rows.nth(0).locator(":scope > td")
        self.assertIn("PluginTema candidate", candidate_cells.nth(1).inner_text())
        self.assertIn("Divi Extended", candidate_cells.nth(3).inner_text())
        self.assertIn("Sem correspondência", candidate_cells.nth(4).inner_text())
        self.assertIn("Pendente", candidate_cells.nth(5).inner_text())
        self.assertIn("Revisar o candidato", candidate_cells.nth(6).inner_text())
        self.assertIn("Diagnóstico", candidate_cells.nth(6).inner_text())
        self.assertIn("—", rows.nth(2).locator(":scope > td").nth(1).inner_text())
        self.assertIn("—", rows.nth(4).locator(":scope > td").nth(1).inner_text())
        self.assertIn("—", rows.nth(6).locator(":scope > td").nth(2).inner_text())

    def test_candidate_controls_and_both_modals(self) -> None:
        self.render_representative_rows()
        row = self.page.locator("#comparison_rows tr").first
        confirm = row.locator(".comparison-confirm-candidate")
        reject = row.locator(".comparison-reject-candidate")
        others = row.locator(".comparison-view-candidates")
        self.assertTrue(confirm.is_visible())
        self.assertTrue(reject.is_visible())
        self.assertTrue(others.is_visible())
        self.assertEqual(confirm.get_attribute("title"), "Confirmar vínculo com o candidato principal")
        self.assertEqual(reject.get_attribute("aria-label"), "Rejeitar candidato principal")
        self.assertEqual(row.locator(".comparison-candidate-actions > button").count(), 3)

        self.page.on("dialog", lambda dialog: dialog.dismiss())
        confirm.click()
        reject.click()
        self.assertTrue(confirm.is_enabled())
        self.assertTrue(reject.is_enabled())

        others.focus()
        others.click()
        link_modal = self.page.locator("#comparison_link_modal")
        self.assertTrue(link_modal.is_visible())
        self.page.keyboard.press("Escape")
        self.assertFalse(link_modal.is_visible())
        self.assertTrue(others.evaluate("node => document.activeElement === node"))
        others.click()
        link_modal.locator(".comparison-link-modal-backdrop").click(position={"x": 2, "y": 2})
        self.assertFalse(link_modal.is_visible())
        self.assertTrue(others.evaluate("node => document.activeElement === node"))

        diagnostic = row.locator(".comparison-recommendation .comparison-diagnostic-open")
        diagnostic.click()
        diagnostic_modal = self.page.locator("#comparison_diagnostic_modal")
        self.assertTrue(diagnostic_modal.is_visible())
        diagnostic_modal.locator(".comparison-link-modal-backdrop").click(position={"x": 2, "y": 2})
        self.assertFalse(diagnostic_modal.is_visible())
        self.assertTrue(diagnostic.evaluate("node => document.activeElement === node"))
        diagnostic.click()
        self.page.keyboard.press("Escape")
        self.assertFalse(diagnostic_modal.is_visible())
        self.assertTrue(diagnostic.evaluate("node => document.activeElement === node"))

        no_candidate = self.page.locator("#comparison_rows tr").nth(2)
        self.assertIn("Nenhum candidato", no_candidate.locator(":scope > td").nth(3).inner_text())
        self.assertEqual(no_candidate.locator(".comparison-candidate-actions").count(), 0)


if __name__ == "__main__":
    unittest.main()
