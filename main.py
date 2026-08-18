from __future__ import annotations

import os
import sys

from app.configuration import WINDOWS_USER_ENVIRONMENT_KEYS


def load_windows_user_environment() -> dict[str, bool]:
    """Load the app's persisted user configuration without logging values."""
    presence = {key: bool(os.getenv(key, "").strip()) for key in WINDOWS_USER_ENVIRONMENT_KEYS}
    if sys.platform != "win32":
        return presence

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment:
            for key in WINDOWS_USER_ENVIRONMENT_KEYS:
                if presence[key]:
                    continue
                try:
                    value, _kind = winreg.QueryValueEx(environment, key)
                except FileNotFoundError:
                    continue
                normalized = str(value or "").strip()
                if normalized:
                    os.environ[key] = normalized
                    presence[key] = True
    except OSError:
        pass
    return presence


load_windows_user_environment()

from app.operations.runtime_repair import repair_update_runtime
from app.operations.transient_recovery import recover_interrupted_preparations

repair_update_runtime()
recover_interrupted_preparations()

from app.app import ScraperApp
from app.resume_policy import install_resume_policy
from app.update_recovery_policy import install_update_recovery_policy
from app.search_ui_policy import install_search_ui_policy
from app.accordion_cleanup_policy import install_accordion_cleanup_policy
from app.session_validation_policy import install_session_validation_policy
from app.update_flow_fix_policy import install_update_flow_fix_policy
from app.staging_reuse_policy import install_staging_reuse_policy
from app.update_operational_ui_policy import install_update_operational_ui_policy
from app.update_reset_policy import install_update_reset_policy
from app.default_queue_clear_policy import install_default_queue_clear_policy
from app.store_category_table_policy import install_store_category_table_policy
from app.store_pack_variation_policy import install_store_pack_variation_policy
from app.store_pack_variation_ui_policy import install_store_pack_variation_ui_policy
from app.comparison_actions_layout_policy import install_comparison_actions_layout_policy
from app.models import ScraperContext, build_context
from app.storage import (
    build_context_paths,
    ensure_slot_dir,
    ensure_slots_root_dir,
    get_active_slot_name,
    load_slots_meta,
)
from app.web import serve

install_resume_policy()
install_update_recovery_policy()
install_search_ui_policy()
install_accordion_cleanup_policy()
install_session_validation_policy()
install_update_flow_fix_policy()
# Comparação: ações principais ficam junto da seleção dos dois catálogos.
install_comparison_actions_layout_policy()
# Loja: Plugins/Temas continuam em lote por categoria, exibidos como tabela por variação.
install_store_category_table_policy()
# Packs: expõe e edita as variações Anual/Vitalícia quando elas existem no WooCommerce.
install_store_pack_variation_policy()
install_store_pack_variation_ui_policy()
# Atualizações: fluxo normal, sem inventário/UI de ZIPs locais.
install_staging_reuse_policy()
install_update_operational_ui_policy()
# Limpar histórico/fila significa resetar o estado local como se os jobs ainda não tivessem sido processados.
install_update_reset_policy()
# Limpar uma lista remove de fato seus jobs materializados e evita reaparecimento imediato da mesma aprovação.
install_default_queue_clear_policy()


def prepare_environment(slot_name: str | None = None) -> str:
    ensure_slots_root_dir()
    load_slots_meta()
    active_slot = slot_name or get_active_slot_name()
    ensure_slot_dir(active_slot)
    return active_slot


def build_default_context(slot_name: str | None = None) -> ScraperContext:
    active_slot = prepare_environment(slot_name)
    context = build_context(slot_name=active_slot)
    build_context_paths(context, ensure=True)
    return context


def build_app(
    slot_name: str | None = None,
    *,
    auto_load_summary: bool = True,
) -> ScraperApp:
    context = build_default_context(slot_name)
    return ScraperApp(context=context, auto_load_summary=auto_load_summary)


def main() -> None:
    load_windows_user_environment()
    app = build_app()
    serve(app)


if __name__ == "__main__":
    main()
