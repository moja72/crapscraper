from __future__ import annotations

import re
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None

# A UI operacional substitui os renderizadores antigos da aba Adicionar, mas os
# endpoints/funcoes de backend continuam disponiveis para o motor de cadastro.
#
# IMPORTANTE: existem tres camadas antigas que mexem no mesmo DOM:
# - new_product_workflow.js recria tab_panel_adicoes com innerHTML;
# - addition_one_click.js observa o documento e decora a lista antiga;
# - addition_chatgpt_assist.js observa o documento e consulta /adicoes/data
#   periodicamente mesmo quando a UI antiga ja nao existe.
#
# A ultima delas foi a causa comprovada do polling legado de /adicoes/data que
# continuava ativo apos a refatoracao operacional.
_LEGACY_RENDER_PATTERNS = (
    re.compile(r"\s*<style\s+data-new-product-workflow(?:=[^>]*)?>.*?</style>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-new-product-workflow-script(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
    # Compatibilidade com builds antigos que eventualmente tenham usado o nome sem -script.
    re.compile(r"\s*<script\s+data-new-product-workflow(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-addition-one-click(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
    re.compile(r"\s*<script\s+data-addition-chatgpt-assist(?:=[^>]*)?>.*?</script>\s*", re.I | re.S),
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
    # O cache/deduplicacao e instalado depois da fila operacional, portanto nao
    # muda o motor de cadastro; apenas evita leituras/sincronizacoes repetidas.
    install_addition_operational_performance_policy()
    # Esta bridge apenas projeta processos operacionais no modal global existente.
    install_addition_processes_bridge_policy()
    # Instrumentacao read-only mantida nesta branch ate a validacao final do bug.
    install_addition_tab_diagnostics_policy()
    _INSTALLED = True
