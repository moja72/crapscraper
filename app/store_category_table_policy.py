from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web
from app.store_custom_fields_quality_policy import install_store_custom_fields_quality_policy
from app.store_quality_unified_policy import install_store_quality_unified_policy

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_category_table.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-store-category-table>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_store_category_table_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
    install_store_custom_fields_quality_policy()
    install_store_quality_unified_policy()
