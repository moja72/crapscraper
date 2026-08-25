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


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "process_modal_stability.js"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-process-modal-stability>\n{script}\n</script>\n"
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

    _INSTALLED = True
