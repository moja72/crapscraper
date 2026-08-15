from __future__ import annotations

from pathlib import Path
from typing import Any

import app.web as web

_INSTALLED = False
_ORIGINAL_RENDER_PANEL_PAGE = web.render_panel_page
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_recovery.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    html = _ORIGINAL_RENDER_PANEL_PAGE(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html

    # Evita encerrar acidentalmente o bloco caso o arquivo venha a conter essa sequência.
    script = script.replace("</script>", "<\\/script>")
    marker = "</body>"
    block = f"\n<script data-update-recovery-ui>\n{script}\n</script>\n"
    if marker in html:
        return html.replace(marker, block + marker, 1)
    return html + block


def install_update_recovery_policy() -> None:
    """Instala uma camada aditiva de recuperação sem reescrever o painel principal."""
    global _INSTALLED
    if _INSTALLED:
        return
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
