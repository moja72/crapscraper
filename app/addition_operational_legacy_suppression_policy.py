from __future__ import annotations

import re
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None

_LEGACY_SCRIPT_PATTERNS = (
    re.compile(r"\s*<script\s+data-new-product-workflow>.*?</script>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-addition-one-click>.*?</script>\s*", re.I | re.S),
)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    for pattern in _LEGACY_SCRIPT_PATTERNS:
        html = pattern.sub("\n", html)
    return html


def install_addition_operational_legacy_suppression_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    from app.addition_processes_bridge_policy import install_addition_processes_bridge_policy
    from app.addition_operational_performance_policy import install_addition_operational_performance_policy

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    # O cache/deduplicação é instalado depois da fila operacional, portanto não
    # muda o motor de cadastro; apenas evita leituras/sincronizações repetidas.
    install_addition_operational_performance_policy()
    # Esta bridge só decora o modal global Processos existente.
    install_addition_processes_bridge_policy()
    _INSTALLED = True
