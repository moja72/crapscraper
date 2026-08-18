from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SCRIPT_PATHS = (
    ("store-pack-variation-table", _STATIC_DIR / "store_pack_variation_table.js"),
    ("store-ui-polish", _STATIC_DIR / "store_ui_polish.js"),
)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    blocks: list[str] = []
    for marker, path in _SCRIPT_PATHS:
        try:
            script = path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
        except OSError:
            continue
        blocks.append(f"\n<script data-{marker}>\n{script}\n</script>\n")
    if not blocks:
        return html
    block = "".join(blocks)
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_store_pack_variation_ui_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
