from __future__ import annotations

from pathlib import Path
from typing import Any

import app.web as web

_INSTALLED = False
_ORIGINAL_RENDER_PANEL_PAGE = web.render_panel_page
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "unified_search_ui.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    html = _ORIGINAL_RENDER_PANEL_PAGE(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html
    script = script.replace("</script>", "<\\/script>")
    block = f"\n<script data-unified-search-ui>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_search_ui_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
