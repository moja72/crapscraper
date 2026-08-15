from __future__ import annotations

import tempfile
import unittest
import re
import shutil
from pathlib import Path
from unittest.mock import patch

from app import comparison, comparison_decisions, settings


ROOT = Path(__file__).resolve().parents[1]


class ComparisonUiContractTests(unittest.TestCase):
    def test_main_navigation_uses_connected_tab_style(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        self.assertIn('class="tabs-nav main-tabs-nav" role="tablist"', web)
        main_tabs = web.split('class="tabs-nav main-tabs-nav"', 1)[1].split('class="page-head-sticky"', 1)[0]
        self.assertEqual(main_tabs.count('role="tab"'), 4)
        self.assertIn('button.setAttribute("aria-selected", active ? "true" : "false")', js)
        self.assertIn(".main-tabs-nav .tab-btn.is-active", css)
        self.assertIn("background: transparent", css)
        self.assertIn("transform: translateY(-4px)", css)
        self.assertIn(".main-tabs-nav::before", css)
        self.assertIn("content: none", css.split(".main-tabs-nav::before", 1)[1].split("}", 1)[0])
        self.assertIn("border-bottom: 0", css.split(".main-tabs-nav {", 1)[1].split("}", 1)[0])
        self.assertIn("border-bottom: 0", css.split(".main-tabs-nav .tab-btn {", 1)[1].split("}", 1)[0])
        active_rule = css.split(".main-tabs-nav .tab-btn.is-active", 1)[1].split("}", 1)[0]
        self.assertIn("border-bottom: 0", active_rule)

    def test_comparison_has_clear_guidance_and_loading_feedback(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn("Para evitar associações incorretas", web)
        self.assertIn("os demais casos ficam disponíveis para revisão", web)
        self.assertIn("Comparando, aguarde...", js)
        self.assertIn('runButton.setAttribute("aria-busy", "true")', js)
        self.assertIn('class="inline-loading-spinner"', js)

    def test_comparison_log_and_last_result_cache(self) -> None:
        combined = (ROOT / "app" / "web.py").read_text(encoding="utf-8") + (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        for token in (
            'id="comparison_log"', 'id="comparison_copy_log"', "appendComparisonLog",
            "COMPARISON_CACHE_KEY", "saveComparisonCache", "restoreComparisonCache",
            "window.localStorage.setItem", "Último resultado restaurado do cache",
        ):
            self.assertIn(token, combined)

    def test_result_uses_origin_and_plugintema_product_permalink(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        self.assertIn('class="card updates-card-section updates-technical-log comparison-technical-log"', web)
        self.assertIn('<span class="comparison-pair-label">Origem</span>', js)
        self.assertIn('const siteProductUrl = normalizeText(row.site_product_url)', js)
        self.assertIn('link(siteProductUrl, "Abrir produto")', js)
        self.assertNotIn('link(row.site_official_url, "Abrir produto")', js)

    def test_table_uses_seven_columns_and_status_owns_selection(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        table_head = web.split('<table class="comparison-table">', 1)[1].split("</thead>", 1)[0]
        table_row = js.split("return `<tr>", 1)[1].split("</tr>`;", 1)[0]
        self.assertEqual(len(re.findall(r"<th(?:\s|>)", table_head)), 7)
        self.assertEqual(len(re.findall(r"<td(?:\s|>)", table_row)), 7)
        self.assertIn('colspan="7"', comparison_markup := web.split('<table class="comparison-table">', 1)[1].split("</table>", 1)[0])
        self.assertIn('colspan="7"', js)
        self.assertNotIn('colspan="10"', comparison_markup)
        expected_headers = [
            "Situação", "Produtos", "Versões", "Candidato principal",
            "Correspondência", "Decisão", "Recomendação",
        ]
        self.assertEqual(re.findall(r"<th>(.*?)</th>", table_head, re.S), expected_headers)
        self.assertIn('<td class="comparison-status-cell">', js)
        self.assertNotIn("comparison-select-column", web + js + css)
        self.assertNotIn("overflow-wrap: anywhere", css)

    def test_modal_controller_and_accessibility_contract(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        for marker in (
            'id="comparison_link_modal"',
            'aria-modal="true"',
            'aria-live="polite"',
            "openComparisonLinkModal",
            "closeComparisonLinkModal",
            'event.key === "Escape"',
            "runComparisonModalSearch",
            "refreshComparison({",
            "force: true",
            'id="comparison_diagnostic_modal"',
            'aria-labelledby="comparison_diagnostic_modal_title"',
            "openComparisonDiagnosticModal",
            "closeComparisonDiagnosticModal",
            "trapComparisonModalFocus",
            "opener.focus()",
        ):
            self.assertIn(marker, web + js)

    def test_compact_candidate_actions_and_version_slots(self) -> None:
        web = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "panel.css").read_text(encoding="utf-8")
        primary = js.split('class="comparison-primary-candidate"', 1)[1].split("const disputedCandidateCount", 1)[0]
        self.assertLess(primary.index("comparison-confirm-candidate"), primary.index("comparison-reject-candidate"))
        self.assertLess(primary.index("comparison-reject-candidate"), primary.index("comparison-view-candidates"))
        self.assertIn('aria-label="Confirmar vínculo com o candidato principal"', primary)
        self.assertIn('aria-label="Rejeitar candidato principal"', primary)
        self.assertIn('title="Confirmar vínculo com o candidato principal"', primary)
        self.assertIn("normalizeText(row.site_version)", js)
        self.assertIn("normalizeText(row.source_version)", js)
        self.assertGreaterEqual(js.count('<span class="comparison-pair-arrow" aria-hidden="true">→</span>'), 2)
        self.assertNotIn("Nível Correspondência", web + js + css)
        for percentage in ("10%", "25%", "11%", "19%", "13%", "12%"):
            self.assertIn(f"width: {percentage}", css)
        self.assertIn("comparison-product-id", js + css)


class ComparisonRelationshipTests(unittest.TestCase):
    def test_catalog_key_validation(self) -> None:
        rows = [{"source_product_key": "source:1"}]
        with patch.object(comparison, "_read_csv_rows", return_value=[]), patch.object(
            comparison, "_normalize_source_rows", return_value=rows
        ), patch.object(Path, "is_file", return_value=True):
            self.assertTrue(
                comparison.comparison_catalog_has_product(
                    "catalog.csv", role="source", product_key="source:1"
                )
            )
            self.assertFalse(
                comparison.comparison_catalog_has_product(
                    "catalog.csv", role="source", product_key="missing"
                )
            )

    def test_confirm_and_reject_use_only_temporary_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "relationships.sqlite3"
            operational = ROOT / "data" / "comparison_decisions.sqlite3"
            if operational.is_file():
                shutil.copy2(operational, database)
            with patch.object(settings, "COMPARISON_DECISIONS_DB_PATH", database):
                first = comparison_decisions.save_relationship(
                    "site:1", "source:1", "manual_confirmed"
                )
                rejected = comparison_decisions.save_relationship(
                    "site:1", "source:1", "manual_rejected"
                )
                second = comparison_decisions.save_relationship(
                    "site:1", "source:2", "manual_confirmed"
                )
            self.assertEqual(first["relationship_state"], "manual_confirmed")
            self.assertEqual(rejected["relationship_state"], "manual_rejected")
            self.assertEqual(second["relationship_state"], "manual_confirmed")
            self.assertTrue(database.is_file())


if __name__ == "__main__":
    unittest.main()
