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
    # créditos deve ser iniciada durante a abertura do painel.
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

    # This policy is installed immediately after download contract v2 in main.py.
    # Attach the final store-validation bridge here so the legacy REST projection
    # cannot overwrite/reject the authoritative local download contract.
    install_addition_download_validation_bridge_policy()

    # PluginTheme bundles can expose their entitlement with a different explicit
    # access flag and renewed profiles may store the bearer token as a raw value.
    # Install this after all addition/session wrappers so Retry uses the upgraded
    # token reader and authorization contract without rebuilding prepared stages.
    install_addition_plugintheme_entitlement_recovery_policy()

    # Regra permanente: o produto agregado "500 CodeCanyon Plugins" nunca deve
    # entrar no fluxo Adicionar, mesmo que um registro antigo não tenha URL salva.
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

    # Comparação > Gerenciar catálogos PluginTema: adiciona atualização in-place,
    # cache incremental do WooCommerce e preservação dos filtros/categorias nativos.
    install_plugintema_catalog_refresh_policy()

    # Loja > Preços: serve planos e packs a partir de cache persistente, mantém uma
    # cópia visual no navegador e só consulta o WooCommerce em background quando
    # ainda não há cache ou quando o usuário pede explicitamente uma atualização.
    install_store_pricing_cache_policy()

    # Resumo superior compartilhado entre Atualizar e Adicionar.
    install_operational_overview_standardization_policy()

    # As duas listas de aprovados usam o mesmo componente visual e operacional.
    install_preparation_standardization_policy()

    # A infraestrutura de fila continua ativa por baixo para compatibilidade e
    # persistência, mas a camada canônica abaixo a remove da experiência visível.
    install_queue_standardization_policy()

    # O gerenciador de Listas de Adições continua disponível internamente para
    # compatibilidade dos dados existentes, sem fazer parte do fluxo principal.
    install_list_manager_standardization_policy()
    install_list_manager_visual_polish_policy()

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    # Histórico permanece como área final comum das duas operações.
    install_history_standardization_policy()

    # A v2 precisa ser instalada ANTES da policy v1: seu script é renderizado
    # primeiro e marca a antiga camada visual como instalada. A policy v1 ainda
    # instala somente o backend /operacoes/simples/* e suas travas de segurança.
    install_operational_simple_flow_v2_policy()
    install_operational_simple_flow_policy()

    # O fluxo canônico recupera uma única vez falhas transitórias de sessão e
    # staging, sem repetir execução remota nem afrouxar as travas do helper.
    install_operational_simple_flow_recovery_policy()

    # A camada final preserva todas as travas e, se alguma pré-condição bloquear,
    # informa exatamente qual predicado falhou em vez da mensagem genérica.
    install_operational_simple_flow_execution_policy()

    # Erros do histórico de atualização reutilizam o mesmo fluxo seguro em uma
    # nova tentativa e, quando concluem, migram naturalmente para Concluídos.
    install_update_history_retry_policy()

    # Abertura do painel: não releia catálogos/logs de todos os runs antes do
    # socket HTTP existir. A hidratação do contexto ativo ocorre em background.
    # Instalada por último para também neutralizar probes remotos adicionados por
    # wrappers visuais anteriores.
    install_startup_fast_path_policy()

    _INSTALLED = True
