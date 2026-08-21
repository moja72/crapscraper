from __future__ import annotations

import re
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None

# A UI operacional substitui apenas os renderizadores legados. Os endpoints e
# funções de backend continuam disponíveis para ações manuais/compatibilidade.
#
# IMPORTANTE: new_product_workflow_policy injeta o JavaScript com o atributo
# data-new-product-workflow-script (e o CSS com data-new-product-workflow).
# A versão anterior desta policy procurava data-new-product-workflow no <script>,
# então o JavaScript antigo continuava ativo e fazia panel.innerHTML=... ao abrir
# Adicionar, concorrendo diretamente com addition_operational_ui.js.
_LEGACY_RENDER_PATTERNS = (
    re.compile(r"\s*<style\s+data-new-product-workflow(?:=[^>]*)?>.*?</style>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-new-product-workflow-script(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
    # Compatibilidade com builds antigos que eventualmente tenham usado o nome sem -script.
    re.compile(r"\s*<script\s+data-new-product-workflow(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-addition-one-click(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
)


def _suppress_legacy_addition_renderers(html: str) -> str:
    result = str(html or "")
    for pattern in _LEGACY_RENDER_PATTERNS:
        result = pattern.sub("\n", result)
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    return _suppress_legacy_addition_renderers(base(*args, **kwargs))


def install_addition_operational_legacy_suppression_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    from app.addition_processes_bridge_policy import install_addition_processes_bridge_policy
    from app.addition_operational_performance_policy import install_addition_operational_performance_policy
    from app.addition_tab_diagnostics_policy import install_addition_tab_diagnostics_policy

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    # O cache/deduplicação é instalado depois da fila operacional, portanto não
    # muda o motor de cadastro; apenas evita leituras/sincronizações repetidas.
    install_addition_operational_performance_policy()
    # Esta bridge só decora o modal global Processos existente.
    install_addition_processes_bridge_policy()
    # Instrumentação read-only da troca de aba. Usada somente nesta branch de diagnóstico.
    install_addition_tab_diagnostics_policy()
    _INSTALLED = True
