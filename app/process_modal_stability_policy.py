from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web
from app.addition_download_validation_bridge_policy import (
    install_addition_download_validation_bridge_policy,
)
from app.addition_plugintheme_entitlement_recovery_policy import (
    install_addition_plugintheme_entitlement_recovery_policy,
)
from app.addition_pack_ignore_policy import install_addition_pack_ignore_policy
from app.update_cross_source_latest_policy import install_update_cross_source_latest_policy
from app.update_site_version_drift_policy import install_update_site_version_drift_policy
from app.update_prepare_plan_reliability_policy import install_update_prepare_plan_reliability_policy
from app.plugintema_catalog_refresh_policy import install_plugintema_catalog_refresh_policy
from app.store_pricing_cache_policy import install_store_pricing_cache_policy
from app.operational_overview_standardization_policy import (
    install_operational_overview_standardization_policy,
)
from app.preparation_standardization_policy import (
    install_preparation_standardization_policy,
)
from app.queue_standardization_policy import install_queue_standardization_policy
from app.list_manager_standardization_policy import install_list_manager_standardization_policy
from app.list_manager_visual_polish_policy import install_list_manager_visual_polish_policy
from app.history_standardization_policy import install_history_standardization_policy
from app.operational_simple_flow_v2_policy import install_operational_simple_flow_v2_policy
from app.operational_simple_flow_policy import install_operational_simple_flow_policy
from app.operational_simple_flow_recovery_policy import (
    install_operational_simple_flow_recovery_policy,
)
from app.operational_simple_flow_execution_policy import (
    install_operational_simple_flow_execution_policy,
)
from app.update_history_retry_policy import install_update_history_retry_policy
from app.update_recoverability_policy import install_update_recoverability_policy
from app.update_metadata_preflight_policy import install_update_metadata_preflight_policy
from app.update_recovery_finalizer_policy import install_update_recovery_finalizer_policy
from app.server_manager_binding_policy import install_server_manager_binding_policy
from app.startup_fast_path_policy import install_startup_fast_path_policy
from app.startup_remote_io_guard_policy import install_startup_remote_io_guard_policy


# Este módulo é importado por main.py antes da sequência de install_* começar.
# A proteção precisa entrar AQUI, e não dentro de install_process_modal_stability_policy,
# porque addition_operational_ui_policy faz uma sincronização durante sua própria
# instalação e o contrato de downloads a transformava em dezenas de requests
# WooCommerce/SSH antes de a porta 8765 existir.
install_startup_remote_io_guard_policy()


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "process_modal_stability.js"
_TECHNICAL_LOG_SCRIPT_PATH = (
    Path(__file__).resolve().parent / "static" / "update_technical_log_fix.js"
)
_PROCESS_HISTORY_OBSERVER_BOOT = (
    "    decorateModal();\n"
    "    observeUi();\n"
    "    window.setTimeout(pollCredits, 900);"
)
_PROCESS_HISTORY_SAFE_BOOT = (
    "    decorateModal();\n"
    "    // Sem MutationObserver global e sem consulta autenticada no boot.\n"
    "    // Créditos/histórico são carregados somente quando Processos é aberto."
)


def _script_block(path: Path, attribute: str) -> str:
    try:
        script = path.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script {attribute}>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    # Defesa para checkouts que ainda carreguem uma versão antiga do bridge de
    # Processos: nenhum MutationObserver global nem consulta autenticada de
    # créditos deve ser iniciado durante a abertura do painel.
    html = html.replace(_PROCESS_HISTORY_OBSERVER_BOOT, _PROCESS_HISTORY_SAFE_BOOT)

    block = _script_block(_SCRIPT_PATH, "data-process-modal-stability")
    block += _script_block(_TECHNICAL_LOG_SCRIPT_PATH, "data-update-technical-log-fix")
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_process_modal_stability_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    install_addition_download_validation_bridge_policy()
    install_addition_plugintheme_entitlement_recovery_policy()
    install_addition_pack_ignore_policy()

    # Atualizações normais passam a comparar PluginTheme e UltraPackV2 ao vivo e
    # escolhem automaticamente a maior versão disponível antes de preparar o ZIP.
    install_update_cross_source_latest_policy()

    # Se o WooCommerce avançou desde a comparação, mas ainda está abaixo da fonte,
    # o estado atual passa a ser a nova base segura do plano em vez de bloquear.
    install_update_site_version_drift_policy()

    # PREPARAR e PLANO viram uma transição confiável: preview válido já materializa
    # o plano e uma rematerialização não pode rebaixar a versão descoberta ao vivo.
    install_update_prepare_plan_reliability_policy()

    install_plugintema_catalog_refresh_policy()
    install_store_pricing_cache_policy()
    install_operational_overview_standardization_policy()
    install_preparation_standardization_policy()
    install_queue_standardization_policy()
    install_list_manager_standardization_policy()
    install_list_manager_visual_polish_policy()

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    install_history_standardization_policy()
    install_operational_simple_flow_v2_policy()
    install_operational_simple_flow_policy()
    install_operational_simple_flow_recovery_policy()
    install_operational_simple_flow_execution_policy()
    install_update_history_retry_policy()

    # Abertura do painel: não releia catálogos/logs de todos os runs antes do
    # socket HTTP existir. A hidratação do contexto ativo ocorre em background.
    install_startup_fast_path_policy()

    # Camada final do fluxo Atualizar: retry é uma nova tentativa real, não uma
    # simples repetição do preview antigo. Revalida fonte/WooCommerce, reaproveita
    # ZIP local só com SHA+versão, permite reconstruir arquivo remoto ausente e
    # consolida os logs de preparação + execução + tentativas anteriores.
    install_update_recoverability_policy()

    # Mesmo quando owner/group/mode não chegaram ao preview, o helper faz um
    # inspect read-only antes da troca. Erros puramente de metadados são migrados
    # para a estratégia transacional controlada, sem exigir correção manual.
    install_update_metadata_preflight_policy()

    # Se uma falha ocorrer depois de preservar o ZIP antigo por rename e antes de
    # instalar o novo .new, restaure o backup automaticamente. Isso fecha a janela
    # em que produção poderia ficar sem ZIP embora a escrita nova não tivesse sido concluída.
    install_update_recovery_finalizer_policy()

    # As rotas finais de retry precisam do mesmo ScraperRunManager capturado pelo
    # Handler original para reutilizar sessões do navegador e contexto ativo.
    install_server_manager_binding_policy()

    _INSTALLED = True
