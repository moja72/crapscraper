from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_ASSET_READER: Callable[[str], str | None] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "unified_search_ui.js"

_PAGE_SIZE_DECLARATION = "const LISTING_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 250];"
_PAGE_SIZE_DECLARATION_WITH_FIVE = "const LISTING_PAGE_SIZE_OPTIONS = [5, 10, 25, 50, 100, 250];"

_PAGINATION_BRIDGE = r"""

  // API pequena e explícita para a camada visual de paginação. Assim o campo
  // "Página X de Y" altera o estado real de cada listagem, sem simular dezenas
  // de cliques nos botões Anterior/Próxima.
  window.__crapscraperPagination = Object.assign(window.__crapscraperPagination || {}, {
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
    pluginTemaManager(page) {
      UI.plugintemaManagePage = Math.max(1, toInt(page, 1));
      renderPluginTemaManagedRows();
    },
    catalogPreview(page) {
      setCatalogPreviewPage(page);
    },
  });
"""


def _patch_panel_javascript(source: str) -> str:
    """Expõe paginação real e inclui 5 itens sem reescrever o painel inteiro."""
    if not source:
        return source

    patched = source.replace(
        _PAGE_SIZE_DECLARATION,
        _PAGE_SIZE_DECLARATION_WITH_FIVE,
        1,
    )

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
    html = base(*args, **kwargs)
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
