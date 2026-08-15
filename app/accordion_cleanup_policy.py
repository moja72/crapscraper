from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "accordion_cleanup.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html

    script = script.replace("</script>", "<\\/script>")
    block = f"\n<script data-accordion-cleanup>\n{script}\n</script>\n"
    marker = "</body>"

    if marker in html:
        return html.replace(marker, block + marker, 1)
    return html + block


def install_accordion_cleanup_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
