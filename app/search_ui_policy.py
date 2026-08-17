from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_ASSET_READER: Callable[[str], str | None] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "unified_search_ui.js"
_PREPARATION_BULK_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "preparation_bulk_ui.js"
_PAGINATION_AUTOJUMP_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "pagination_autojump.js"
_UI_REFINEMENTS_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "ui_refinements.js"
_HISTORY_TABS_FIX_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "history_tabs_fix.js"
_RUN_TABS_HISTORY_STYLE_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "run_tabs_history_style.js"
_UPDATE_LISTS_MANAGER_UI_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_lists_manager_ui.js"
_SELECT_INDICATOR_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "select_indicator.js"
_UPDATE_LOADING_UI_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_loading_ui.js"
_CATALOG_CARDS_REFINEMENT_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "catalog_cards_refinement.js"

_PAGE_SIZE_SELECT_IDS = (
    "catalogos_page_size",
    "comparison_page_size",
    "plugintema_manage_page_size",
    "updates_page_size",
    "updates_queue_page_size",
    "updates_history_page_size",
    "update_list_preview_page_size",
    "catalog_preview_page_size",
)

_JS_REPLACEMENTS = (
    (
        'return name.toLowerCase() === "default" ? "Principal" : name;',
        'return name.toLowerCase() === "default" ? "Padrão" : name;',
    ),
    (
        'defaultButton.textContent = selectedIsDefault ? "⭐ Default atual" : "⭐ Default";',
        'defaultButton.textContent = selectedIsDefault ? "⭐ Padrão atual" : "⭐ Padrão";',
    ),
    ("como catálogo default", "como catálogo padrão"),
    (
        'notify(result?.message || "Slot default alterado.");',
        'notify(result?.message || "Catálogo padrão alterado.");',
    ),
    (
        '<div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version || "-")} → ${escapeHtml(job.effective_source_version || job.ultrapack_version || "-")}</div><div class="small">Relacionamento: ${escapeHtml(updateRelationshipLabel(job.relationship))}</div>',
        '<div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version || "-")} → ${escapeHtml(job.effective_source_version || job.ultrapack_version || "-")}</div><div class="small">Origem: ${escapeHtml(updateSourceLabel(job))} · Relacionamento: ${escapeHtml(updateRelationshipLabel(job.relationship))}</div>',
    ),
    (
        '<div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version||"-")} → ${escapeHtml(job.effective_source_version||job.ultrapack_version||"-")}</div>${reason?',
        '<div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version||"-")} → ${escapeHtml(job.effective_source_version||job.ultrapack_version||"-")}</div><div class="small">Origem: ${escapeHtml(updateSourceLabel(job))}</div>${reason?',
    ),
)

_CATALOG_SEARCH_FIELD_PATTERN = re.compile(
    r'\s*<div class="field">\s*'
    r'<label for="catalogos_search">Buscar catálogos e contextos</label>\s*'
    r'<input id="catalogos_search" type="search" placeholder="Nome, site, tipo ou conta">\s*'
    r'</div>',
    re.IGNORECASE | re.DOTALL,
)

_UPDATE_TYPE_FIELD_PATTERN = re.compile(
    r'\s*<div class="field">\s*<label[^>]*for=["\']updates_type_filter["\'][^>]*>.*?</label>\s*'
    r'<select[^>]*id=["\']updates_type_filter["\'][^>]*>.*?</select>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)

_CATALOG_CONTEXT_TOOLBAR = '''<div class="catalogos-table-toolbar">
          <div><div class="section-title catalogos-context-title">Contextos dos catálogos</div><span class="badge" id="catalogos_context_count">0 contextos</span></div>
          <button class="btn-danger" id="catalogos_remove_zero_btn" type="button" disabled>Remover contextos zerados</button>
        </div>'''

_CATALOG_CONTEXT_SEARCH_BLOCK = '''
        <div class="catalogos-context-search cs-search-system" style="margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--bg-elev-1);">
          <div class="field">
            <label for="catalogos_search">Buscar nos contextos</label>
            <input id="catalogos_search" type="search" placeholder="Catálogo, site, tipo ou conta">
          </div>
        </div>'''

_PLUGIN_TEMA_TOOLBAR_ACTION_PATTERN = re.compile(
    r'\s*<button\b[^>]*\bid=["\']plugintema_manage_(?:download|delete)["\'][^>]*>.*?</button>',
    re.IGNORECASE | re.DOTALL,
)

_PAGINATION_BRIDGE = r"""

  function updateSourceLabel(job) {
    const explicit = normalizeText(
      job?.source_site || job?.source_site_key || job?.origin_site || job?.origin || ""
    );
    if (explicit) {
      const normalized = explicit.toLowerCase();
      if (normalized.includes("plugintheme") || normalized.includes("plugin_theme")) return "PluginTheme";
      if (normalized.includes("ultrapack")) return "UltraPackV2";
      return explicit;
    }
    const sourceUrl = normalizeText(
      job?.ultrapack_url || job?.source_product_url || job?.source_url || ""
    ).toLowerCase();
    if (sourceUrl.includes("plugintheme")) return "PluginTheme";
    if (sourceUrl.includes("ultrapack")) return "UltraPackV2";
    return "Origem não informada";
  }

  window.__crapscraperPagination = Object.assign(window.__crapscraperPagination || {}, {
    catalogs(page) {
      UI.catalogPage = Math.max(1, toInt(page, 1));
      loadCatalogosData();
    },
    comparison(page) {
      UI.comparison.page = Math.max(1, toInt(page, 1));
      if (UI.comparison.lastPayload) renderComparison(UI.comparison.lastPayload);
    },
    updatesWaiting(page) {
      UPDATE_QUEUE.page = Math.max(1, toInt(page, 1));
      renderUpdateJobs();
    },
    updatesQueue(page) {
      UPDATE_QUEUE.queuePage = Math.max(1, toInt(page, 1));
      renderOperationalQueue();
    },
    updatesHistory(page) {
      UPDATE_QUEUE.historyPage = Math.max(1, toInt(page, 1));
      renderUpdateHistory();
    },
    updateListPreview(page) {
      UPDATE_QUEUE.previewPage = Math.max(1, toInt(page, 1));
      renderUpdateListPreview();
    },
    pluginTemaManager(page) {
      UI.plugintemaManagePage = Math.max(1, toInt(page, 1));
      renderPluginTemaManagedRows();
    },
    catalogPreview(page) {
      setCatalogPreviewPage(page);
    },
  });
"""


def _patch_page_size_select(html: str, select_id: str) -> str:
    pattern = re.compile(
        rf'(<select\b[^>]*\bid=["\']{re.escape(select_id)}["\'][^>]*>)(.*?)(</select>)',
        re.IGNORECASE | re.DOTALL,
    )

    def repl(match: re.Match[str]) -> str:
        return (f'<input id="{select_id}" class="listing-page-size-input" type="number" '
                'min="1" step="1" value="5" inputmode="numeric" '
                'aria-label="Itens por página">')

    return pattern.sub(repl, html, count=1)


def _patch_catalog_context_search(html: str) -> str:
    if 'id="catalogos_search"' not in html:
        return html
    patched = _CATALOG_SEARCH_FIELD_PATTERN.sub("", html, count=1)
    if 'class="catalogos-context-search cs-search-system"' in patched:
        return patched
    if _CATALOG_CONTEXT_TOOLBAR not in patched:
        return patched
    return patched.replace(
        _CATALOG_CONTEXT_TOOLBAR,
        _CATALOG_CONTEXT_TOOLBAR + _CATALOG_CONTEXT_SEARCH_BLOCK,
        1,
    )


def _patch_plugin_tema_toolbar_actions(html: str) -> str:
    return _PLUGIN_TEMA_TOOLBAR_ACTION_PATTERN.sub("", html)


def _patch_panel_html(html: str) -> str:
    patched = html.replace(
        'id="updates_working_title">Aguardando / preparação</div>',
        'id="updates_working_title">Preparação</div>',
    )
    patched = _UPDATE_TYPE_FIELD_PATTERN.sub("", patched, count=1)
    patched = _patch_catalog_context_search(patched)
    patched = _patch_plugin_tema_toolbar_actions(patched)
    for select_id in _PAGE_SIZE_SELECT_IDS:
        patched = _patch_page_size_select(patched, select_id)
    return patched


def _patch_panel_javascript(source: str) -> str:
    if not source:
        return source
    patched = source
    for old, new in _JS_REPLACEMENTS:
        patched = patched.replace(old, new)
    if "window.__crapscraperPagination" in patched:
        return patched
    marker = "})();"
    position = patched.rfind(marker)
    if position < 0:
        return patched
    return patched[:position] + _PAGINATION_BRIDGE + "\n" + patched[position:]


def _patched_asset_reader(kind: str) -> str | None:
    base = _BASE_ASSET_READER
    content = base(kind) if base is not None else None
    if str(kind or "").strip().lower() == "js" and content:
        return _patch_panel_javascript(content)
    return content


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = _patch_panel_html(base(*args, **kwargs))

    script_blocks: list[str] = []
    for script_path, attribute in (
        (_SCRIPT_PATH, "data-unified-search-ui"),
        (_PREPARATION_BULK_SCRIPT_PATH, "data-preparation-bulk-ui"),
        (_PAGINATION_AUTOJUMP_SCRIPT_PATH, "data-pagination-autojump"),
        (_UI_REFINEMENTS_SCRIPT_PATH, "data-ui-refinements"),
        (_HISTORY_TABS_FIX_SCRIPT_PATH, "data-history-tabs-fix"),
        (_RUN_TABS_HISTORY_STYLE_SCRIPT_PATH, "data-run-tabs-history-style"),
        (_UPDATE_LISTS_MANAGER_UI_SCRIPT_PATH, "data-update-lists-manager-ui"),
        (_SELECT_INDICATOR_SCRIPT_PATH, "data-select-indicator"),
        (_UPDATE_LOADING_UI_SCRIPT_PATH, "data-update-loading-ui"),
        (_CATALOG_CARDS_REFINEMENT_SCRIPT_PATH, "data-catalog-cards-refinement"),
    ):
        try:
            script = script_path.read_text(encoding="utf-8")
        except OSError:
            continue
        script = script.replace("</script>", "<\\/script>")
        script_blocks.append(f"\n<script {attribute}>\n{script}\n</script>\n")

    if not script_blocks:
        return html
    block = "".join(script_blocks)
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_search_ui_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_ASSET_READER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    _BASE_ASSET_READER = web._read_first_existing_asset
    web._read_first_existing_asset = _patched_asset_reader
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
