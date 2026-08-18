from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "comparison_actions_layout.js"

_STYLE = """
<style data-comparison-actions-layout>
#comparison_catalog_actions.comparison-catalog-actions{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,.42fr);gap:10px;margin-top:14px}
#comparison_catalog_actions .comparison-catalog-action-primary,#comparison_catalog_actions .comparison-catalog-action-secondary{width:100%;min-height:46px}
@media(max-width:760px){#comparison_catalog_actions.comparison-catalog-actions{grid-template-columns:1fr}}
</style>
"""


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = _STYLE + f"\n<script data-comparison-actions-layout-script>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_comparison_actions_layout_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
