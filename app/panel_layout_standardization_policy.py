from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATHS = (
    ("data-panel-layout-standardization", Path(__file__).resolve().parent / "static" / "panel_layout_standardization.js"),
    ("data-operational-ui-parity", Path(__file__).resolve().parent / "static" / "operational_ui_parity.js"),
    ("data-operational-ui-final-alignment", Path(__file__).resolve().parent / "static" / "operational_ui_final_alignment.js"),
    ("data-operational-ui-consistency-v4", Path(__file__).resolve().parent / "static" / "operational_ui_consistency_v4.js"),
    ("data-operational-ui-card-parity-v5", Path(__file__).resolve().parent / "static" / "operational_ui_card_parity_v5.js"),
    ("data-operational-ui-card-size-parity-v6", Path(__file__).resolve().parent / "static" / "operational_ui_card_size_parity_v6.js"),
    ("data-operation-completion-visibility", Path(__file__).resolve().parent / "static" / "operation_completion_visibility.js"),
    ("data-preparation-sections-canonical-v8", Path(__file__).resolve().parent / "static" / "preparation_sections_canonical_v8.js"),
    ("data-preparation-sections-canonical-v8-cleanup", Path(__file__).resolve().parent / "static" / "preparation_sections_canonical_v8_cleanup.js"),
    ("data-preparation-update-visibility-v9", Path(__file__).resolve().parent / "static" / "preparation_update_visibility_v9.js"),
    ("data-preparation-flow-gate-v10", Path(__file__).resolve().parent / "static" / "preparation_flow_gate_v10.js"),
    ("data-operational-reliability-v11", Path(__file__).resolve().parent / "static" / "operational_reliability_v11.js"),
    ("data-operational-history-shared-v12", Path(__file__).resolve().parent / "static" / "operational_history_shared.js"),
)
_STYLE_PATHS = (
    ("data-operational-history-shared-style-v12", Path(__file__).resolve().parent / "static" / "operational_history_shared.css"),
)

_ADDITION_PROGRESS_MARKER = (
    '<div class="addition-summary-grid" id="addition_summary_grid"></div>'
    '<div class="addition-guidance" id="addition_guidance">Carregando estado persistido…</div>'
)
_ADDITION_PROGRESS_MARKUP = (
    '<div class="addition-progress-block" id="addition_progress_block">'
    '<div class="updates-progress-copy cs-op-progress-copy">'
    '<strong id="addition_progress_percent">0%</strong>'
    '<span id="addition_progress_label">0 de 0 processados</span>'
    '</div>'
    '<div class="updates-progress-track cs-op-progress-track" role="progressbar" '
    'aria-label="Progresso geral das adições" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">'
    '<span id="addition_progress_bar"></span>'
    '</div>'
    '<div id="addition_now" class="updates-now cs-op-now">Nenhuma adição em execução</div>'
    '</div>'
    + _ADDITION_PROGRESS_MARKER
)
_ADDITION_RENDER_MARKER = '    const counts=state.overview.counts||{},grid=$("#addition_summary_grid");if(!grid)return;\n'
_ADDITION_RENDER_PATCH = _ADDITION_RENDER_MARKER + '''    const additionProgressTotal=Math.max(0,Number(counts.total||0));
    const additionProgressTerminal=Math.max(0,Number(counts.completed||0)+Number(counts.error||0)+Number(counts.interrupted||0)+Number(counts.canceled||0));
    const additionProgressProcessed=Math.min(additionProgressTotal,additionProgressTerminal);
    const additionProgressPercent=additionProgressTotal?Math.round(additionProgressProcessed*100/additionProgressTotal):0;
    const additionProgressPercentNode=$("#addition_progress_percent"),additionProgressLabel=$("#addition_progress_label"),additionProgressBar=$("#addition_progress_bar"),additionNow=$("#addition_now");
    if(additionProgressPercentNode)additionProgressPercentNode.textContent=`${additionProgressPercent}%`;
    if(additionProgressLabel)additionProgressLabel.textContent=`${additionProgressProcessed} de ${additionProgressTotal} processados`;
    if(additionProgressBar){additionProgressBar.style.width=`${additionProgressPercent}%`;additionProgressBar.parentElement?.setAttribute("aria-valuenow",String(additionProgressPercent));}
    if(additionNow){
      if((counts.executing||0)>0)additionNow.textContent=`${counts.executing} produto(s) em cadastro agora`;
      else if((counts.preparing||0)>0)additionNow.textContent=`${counts.preparing} produto(s) em preparação`;
      else if((counts.queued||0)>0)additionNow.textContent=`${counts.queued} produto(s) aguardando execução`;
      else if((counts.ready||0)>0)additionNow.textContent=`${counts.ready} produto(s) prontos para a fila`;
      else if((counts.waiting||0)>0)additionNow.textContent=`${counts.waiting} produto(s) aguardando preparação`;
      else if(additionProgressTotal>0&&additionProgressProcessed>=additionProgressTotal)additionNow.textContent="Processamento concluído";
      else additionNow.textContent="Nenhuma adição em execução";
    }
'''
def _patch_addition_progress(html: str) -> str:
    result = str(html or "")
    if 'id="addition_progress_block"' not in result and _ADDITION_PROGRESS_MARKER in result:
        result = result.replace(_ADDITION_PROGRESS_MARKER, _ADDITION_PROGRESS_MARKUP, 1)
    if "additionProgressTotal" not in result and _ADDITION_RENDER_MARKER in result:
        result = result.replace(_ADDITION_RENDER_MARKER, _ADDITION_RENDER_PATCH, 1)
    return result


def _style_block() -> str:
    blocks: list[str] = []
    for attribute, path in _STYLE_PATHS:
        try:
            style = path.read_text(encoding="utf-8").replace("</style>", "<\\/style>")
        except OSError:
            continue
        blocks.append(f"\n<style {attribute}>\n{style}\n</style>\n")
    return "".join(blocks)


def _script_block() -> str:
    blocks: list[str] = []
    for attribute, path in _SCRIPT_PATHS:
        try:
            script = path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
        except OSError:
            continue
        blocks.append(f"\n<script {attribute}>\n{script}\n</script>\n")
    return "".join(blocks)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = _patch_addition_progress(base(*args, **kwargs))
    block = _style_block() + _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_panel_layout_standardization_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    # As listas da fila de Adições são instaladas aqui porque esta policy já é
    # executada depois da UI operacional e da camada de cache/resiliência. Assim
    # a seleção da lista ativa pode reaproveitar o mesmo motor sem duplicar
    # workers, listeners ou polling.
    from app.addition_queue_lists_policy import install_addition_queue_lists_policy
    from app.operation_completion_visibility_policy import install_operation_completion_visibility_policy
    from app.preparation_execution_gate_policy import install_preparation_execution_gate_policy
    from app.operational_reliability_policy import install_operational_reliability_policy
    from app.operational_history_shared_policy import install_operational_history_shared_policy

    install_addition_queue_lists_policy()
    install_operation_completion_visibility_policy()
    install_preparation_execution_gate_policy()
    install_operational_reliability_policy()
    install_operational_history_shared_policy()
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
