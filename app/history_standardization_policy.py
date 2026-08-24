from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web
from app.operational_history_shared_policy import install_operational_history_shared_policy


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SHARED_CSS = _STATIC_DIR / "operational_history_shared.css"
_SHARED_JS = _STATIC_DIR / "operational_history_shared.js"
_POLISH_CSS = _STATIC_DIR / "history_standardization_v2.css"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    css = "\n".join(part for part in (_read(_SHARED_CSS), _read(_POLISH_CSS)) if part)
    script = _read(_SHARED_JS).replace("</script>", "<\\/script>")
    if not css and not script:
        return html

    block = "\n"
    if css:
        block += f'<style data-history-standardization-v2>\n{css}\n</style>\n'
    if script:
        block += f'<script data-history-standardization-v2>\n{script}\n</script>\n'

    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_history_standardization_policy() -> None:
    """Make Atualizar and Adicionar use one canonical History component.

    The shared backend already normalizes both operational histories.  This final
    presentation layer is intentionally installed after the legacy operational UI
    policies so it owns both history accordions and prevents their old markup from
    drifting apart again.
    """
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    install_operational_history_shared_policy()
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
