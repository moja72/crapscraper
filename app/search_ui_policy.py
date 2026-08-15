from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_ASSET_READER: Callable[[str], str | None] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "unified_search_ui.js"

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
        "const LISTING_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 250];",
        "const LISTING_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100, 250];",
    ),
    (
        "const LISTING_DEFAULT_PAGE_SIZE = 25;",
        "const LISTING_DEFAULT_PAGE_SIZE = 5;",
    ),
    ("plugintemaManagePageSize: 25,", "plugintemaManagePageSize: 5,"),
    ("      pageSize: 100,", "      pageSize: 5,"),
    ("      pageSize: 25,", "      pageSize: 5,"),
    (
        'toInt(byId("comparison_page_size")?.value, 100)',
        'toInt(byId("comparison_page_size")?.value, 5)',
    ),
)

_PAGINATION_BRIDGE = r"""

  // API explícita de paginação para o campo editável "Página X de Y".
  // Cada setter altera o estado real da listagem e solicita o render correto.
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
        opening, options, closing = match.groups()
        options = re.sub(r"\s+selected(?=\s|>)", "", options, flags=re.IGNORECASE)
        option_five = re.compile(
            r'(<option\b[^>]*\bvalue=["\']5["\'][^>]*)(>)',
            re.IGNORECASE,
        )
        if option_five.search(options):
            options = option_five.sub(r"\1 selected\2", options, count=1)
        else:
            options = '<option value="5" selected>5</option>' + options
        return opening + options + closing

    return pattern.sub(repl, html, count=1)


def _patch_panel_html(html: str) -> str:
    patched = html.replace(
        'id="updates_working_title">Aguardando / preparação</div>',
        'id="updates_working_title">Preparação</div>',
    )
    for select_id in _PAGE_SIZE_SELECT_IDS:
        patched = _patch_page_size_select(patched, select_id)
    return patched


def _patch_panel_javascript(source: str) -> str:
    """Aplica defaults reais de paginação e expõe setters usados pela UI."""
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
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html

    script = script.replace("</script>", "<\\/script>")
    block = f"\n<script data-unified-search-ui>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_search_ui_policy() -> None:
    """Instala a padronização visual sem alterar regras de negócio das listagens."""
    global _INSTALLED, _BASE_RENDER, _BASE_ASSET_READER
    if _INSTALLED:
        return

    _BASE_RENDER = web.render_panel_page
    _BASE_ASSET_READER = web._read_first_existing_asset
    web._read_first_existing_asset = _patched_asset_reader
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
