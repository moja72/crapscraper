from pathlib import Path


def test_search_ui_policy_injects_unified_script():
    root = Path(__file__).resolve().parents[1]
    policy = (root / "app" / "search_ui_policy.py").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "unified_search_ui.js").read_text(encoding="utf-8")
    preparation_bulk = (root / "app" / "static" / "preparation_bulk_ui.js").read_text(encoding="utf-8")
    refinements = (root / "app" / "static" / "ui_refinements.js").read_text(encoding="utf-8")

    assert "data-unified-search-ui" in policy
    assert "data-preparation-bulk-ui" in policy
    assert "data-ui-refinements" in policy
    assert "_PREPARATION_BULK_SCRIPT_PATH" in policy
    assert "_UI_REFINEMENTS_SCRIPT_PATH" in policy
    assert "_patch_panel_javascript" in policy
    assert "_patch_panel_html" in policy
    assert "_patch_catalog_context_search" in policy
    assert "_patch_plugin_tema_toolbar_actions" in policy
    assert "const LISTING_DEFAULT_PAGE_SIZE = 5;" in policy
    assert "[5, 10, 25, 50, 100, 250]" in policy
    assert "window.__crapscraperPagination" in policy
    assert 'id="updates_working_title">Preparação</div>' in policy
    assert 'class="catalogos-context-search cs-search-system"' in policy
    assert 'for="catalogos_search">Buscar nos contextos</label>' in policy
    assert 'placeholder="Catálogo, site, tipo ou conta"' in policy
    assert 'data-catalog-action="download">⬇️ Baixar</button>' in policy
    assert 'button.dataset.catalogAction === "download"' in policy
    assert "plugintema_manage_(?:download|delete)" in policy
    assert '"default" ? "Padrão"' in policy
    assert "⭐ Padrão atual" in policy
    assert "como catálogo padrão" in policy

    assert "PAGE_SIZES = [5, 10, 25, 50, 100, 250]" in script
    assert "DEFAULT_PAGE_SIZE = 5" in script
    assert "cs-page-jump" in script
    assert "listing-pagination" in script
    assert "listing-meta-row" in script
    assert "cs-queue-meta-row" in script
    assert "cs-bulk-selection-line" in script
    assert "cs-bulk-action-line" in script
    assert "standardizeQueueMeta" in script
    assert "standardizeWaitingBulk" in script

    assert '"Selecionar página"' in preparation_bulk
    assert '"Selecionar todo resultado"' in preparation_bulk
    assert 'prepare.textContent = "Preparar planos"' in preparation_bulk
    assert 'enqueue.textContent = "Adicionar à fila"' in preparation_bulk
    assert "cs-preparation-actions" in preparation_bulk
    assert "meta.parentElement.insertBefore(bar, meta)" in preparation_bulk

    assert "#runs_manager_card.collect-runs-accordion" in refinements
    assert ".catalogo-status-row" in refinements
    assert ".catalogo-availability-icon.is-unavailable" in refinements
    assert '["📄", "Catálogo", hasCatalog]' in refinements
    assert '["📝", "Estado", hasState]' in refinements
    assert '["📋", "Log", hasLog]' in refinements
    assert ".updates-history-tab.is-active" in refinements
    assert "border-bottom-color:var(--bg-elev-1)" in refinements

    for token in (
        "catalogos_page_size",
        "comparison_page_size",
        "updates_page_size",
        "updates_queue_page_size",
        "updates_history_page_size",
        "update_list_preview_page_size",
        "plugintema_manage_page_size",
        "catalog_preview_page_size",
    ):
        assert token in policy or token in script

    for setter in (
        "catalogs",
        "comparison",
        "updatesWaiting",
        "updatesQueue",
        "updatesHistory",
        "updateListPreview",
        "pluginTemaManager",
        "catalogPreview",
    ):
        assert setter in policy
