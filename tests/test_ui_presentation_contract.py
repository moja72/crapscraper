from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "app" / "web.py").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "panel.css").read_text(encoding="utf-8")
SELECT_INDICATOR = (ROOT / "app" / "static" / "select_indicator.js").read_text(encoding="utf-8")
UPDATE_LOADING = (ROOT / "app" / "static" / "update_loading_ui.js").read_text(encoding="utf-8")


def test_comparison_labels_are_built_in_the_backend_without_legacy_copy():
    source_builder = WEB.split("def _build_comparison_sources_payload", 1)[1].split(
        "def _parse_plugintema_filters", 1
    )[0]
    assert "[Salvo]" not in source_builder
    assert "atualizados em" not in source_builder
    assert "'Padrão' if slot_name.lower() == 'default'" in source_builder
    assert 'f"{items_count:,} itens".replace(",", ".")' in source_builder
    assert '"updated_at": _normalize_spaces(row.get("updated_at"))' in source_builder


def test_queue_checkpoint_is_formatted_at_render_origin_and_aligned_to_select():
    queue_render = JS.split("function renderOperationalQueue()", 1)[1].split(
        "function renderUpdateListsManager()", 1
    )[0]
    assert "formatPtBrDateTime(metadata?.last_completed_at" in queue_render
    assert "formatPtBrInteger(total)" in queue_render
    assert "Última conclusão:" not in queue_render
    assert "arquivo ${metadata.file}" not in queue_render
    assert ".updates-queue-selector>.small{display:flex;align-items:center;align-self:end;min-height:44px" in CSS


def test_refinement_observers_no_longer_reformat_catalogs_or_queue_checkpoint():
    assert "new MutationObserver(schedule)" not in SELECT_INDICATOR
    apply_body = UPDATE_LOADING.split("function applyDisplayFormatting()", 1)[1].split(
        "function readCache()", 1
    )[0]
    assert "formatQueueCheckpoint()" not in apply_body
    assert "formatComparisonCatalogSelectors()" not in apply_body


def test_history_active_tab_and_catalog_download_contract():
    assert ".updates-history-tab.is-active{z-index:1;border-bottom:0;background:#141415" in CSS
    assert 'data-catalog-action="download">⬇️ Baixar</button>' in JS
    assert 'button.dataset.catalogAction === "download"' in JS
