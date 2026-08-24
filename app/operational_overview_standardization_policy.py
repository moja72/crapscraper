from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "operational_overview_standardization.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    # O título do bloco Atualizar é estático no HTML-base. Corrigi-lo aqui deixa a
    # semântica correta já na resposta inicial, antes mesmo da normalização de DOM.
    html = html.replace(
        '<div class="section-title">Atualizações</div><div class="small">Prepare com segurança, revise o plano e execute sequencialmente.</div>',
        '<div class="section-title">Atualiza produtos</div><div class="small">Prepare os produtos aprovados, revise os dados e execute as atualizações com segurança no WooCommerce.</div>',
        1,
    )

    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html

    block = f"\n<script data-operational-overview-standardization>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_operational_overview_standardization_policy() -> None:
    """Instala a camada visual final dos cards de Atualizar e Adicionar.

    A implementação move os nós existentes em vez de cloná-los, preservando IDs,
    listeners e estados mantidos pelas camadas operacionais anteriores.
    """
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
