from __future__ import annotations

from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None

# addition_operational_ui.js mantém o scope dentro de state.loading durante o
# render final. renderHistory/renderRows detectam esse flag e desenham novamente
# o spinner; o finally remove o flag depois, mas não havia uma nova renderização.
# A correção preserva a requisição e move apenas o render final para depois do
# state.loading.delete(scope), inclusive em erro/timeout para nunca deixar spinner.
_SCOPE_RENDER_BEFORE_CLEAR = (
    'Object.assign(data,payload);if(scope==="history"){renderHistory();state.historyDirty=false;}'
    'else renderScope(scope);}catch(error){log(`Falha em ${scope}: ${error.message}`,"ERRO");'
    'if(!silent)toast(error.message,"error");}finally{state.loading.delete(scope);}}'
)

_SCOPE_RENDER_AFTER_CLEAR = (
    'Object.assign(data,payload);if(scope==="history")state.historyDirty=false;}'
    'catch(error){log(`Falha em ${scope}: ${error.message}`,"ERRO");'
    'if(!silent)toast(error.message,"error");}finally{state.loading.delete(scope);'
    'if(scope==="history")renderHistory();else renderScope(scope);}}'
)


def _patch_addition_scope_render(html: str) -> str:
    return str(html or "").replace(_SCOPE_RENDER_BEFORE_CLEAR, _SCOPE_RENDER_AFTER_CLEAR)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    return _patch_addition_scope_render(base(*args, **kwargs))


def install_addition_loading_render_fix_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
