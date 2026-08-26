from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_history_retry.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-update-history-retry>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_update_history_retry_policy() -> None:
    """Adiciona retry aos erros sem criar um segundo executor de atualização.

    O botão reutiliza /operacoes/simples/atualizar, portanto continua passando
    pelo mesmo prepare, SHA-256, vínculo, allowlist, backup e executor controlado.
    Quando o job chega a COMPLETED, o histórico compartilhado já o projeta no
    bucket Concluídos em vez do bucket Erros.
    """
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
