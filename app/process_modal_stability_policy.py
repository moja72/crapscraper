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
from app.update_prepare_plan_reliability_policy import install_update_prepare_plan_reliability_policy


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

    # PREPARAR e PLANO viram uma transição confiável: preview válido já materializa
    # o plano e uma rematerialização não pode rebaixar a versão descoberta ao vivo.
    install_update_prepare_plan_reliability_policy()

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
