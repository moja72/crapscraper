from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "panel.css").read_text(encoding="utf-8")
CARDS = (ROOT / "app" / "static" / "catalog_cards_refinement.js").read_text(encoding="utf-8")
PAGINATION = (ROOT / "app" / "static" / "pagination_autojump.js").read_text(encoding="utf-8")


class CatalogUiRegressionTests(unittest.TestCase):
  def test_catalog_cards_keep_stable_status_and_file_rows(self):
    assert "catalogo-status-row" in JS
    assert "🟢 Atual" in JS
    assert "⭐ Catálogo padrão" in JS
    assert 'aria-hidden="true"' in JS
    for token in ('["📄", "Catálogo", entry.has_csv]', '["📝", "Estado", entry.has_status]', '["📋", "Log", entry.has_log]'):
        assert token in JS
    assert "opacity:.12" in CSS + CARDS
    assert "data-tooltip=\"${label}\"" not in JS
    assert 'title="${label}"' in JS
    assert 'button.textContent = "⬇️ Baixar"' in CARDS


  def test_catalog_controls_and_context_search_order(self):
    modal = WEB.split('id="tab_panel_catalogos"', 1)[1].split('id="tab_panel_fila"', 1)[0]
    assert modal.index('id="catalogos_filter_slot"') < modal.index("catalogos-refresh-field")
    assert modal.index("catalogos-refresh-field") < modal.index("catalogos_cards_wrap")
    assert modal.index("catalogos-context-title") < modal.index('id="catalogos_search"')
    assert "grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in CARDS
    assert "grid-column:auto!important" in CARDS


  def test_preparation_contract_is_restored(self):
    panel = WEB.split('id="tab_panel_atualizacoes"', 1)[1].split('id="tab_panel_loja"', 1)[0]
    assert 'id="updates_working_title">Preparação</div>' in panel
    assert 'id="updates_type_filter"' not in panel
    assert 'id="updates_environment_toggle"' not in panel
    assert 'id="updates_environment_details"' in panel
    assert 'id="updates_environment_details" class="hidden"' not in panel


  def test_every_page_size_defaults_to_five_and_page_is_editable(self):
    ids = (
        "catalogos_page_size", "comparison_page_size", "plugintema_manage_page_size",
        "updates_page_size", "updates_queue_page_size", "updates_history_page_size",
        "update_list_preview_page_size",
    )
    for select_id in ids:
        select = WEB.split(f'id="{select_id}"', 1)[1].split("</select>", 1)[0]
        assert '<option value="5" selected>5</option>' in select
        assert '<option value="10">10</option>' in select
        assert all(f'value="{size}"' not in select for size in (25, 50, 100, 250))
    assert "const LISTING_DEFAULT_PAGE_SIZE = 5" in JS
    assert "const DEBOUNCE_MS = 700" in PAGINATION
    assert 'event.key !== "Enter"' in PAGINATION
    assert "data-cs-page-input" in PAGINATION
    assert 'data-cs-page-input type="number"' in WEB
    for setter in ("catalogs", "comparison", "updatesWaiting", "updatesQueue", "updatesHistory", "updateListPreview", "pluginTemaManager", "catalogPreview"):
        assert f"{setter}(page)" in JS


  def test_refinements_are_loaded_by_the_base_panel(self):
    assert '<script src="/catalog_cards_refinement.js"></script>' in WEB
    assert '<script src="/pagination_autojump.js"></script>' in WEB
    assert 'path in {"/catalog_cards_refinement.js", "/pagination_autojump.js"}' in WEB
