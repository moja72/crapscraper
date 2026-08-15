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


# Precisa ocorrer antes de importar modulos que calculam constantes via getenv.
load_windows_user_environment()


from app.app import ScraperApp
from app.models import ScraperContext, build_context
from app.storage import (
    build_context_paths,
    ensure_slot_dir,
    ensure_slots_root_dir,
    get_active_slot_name,
    load_slots_meta,
)
from app.web import serve


def prepare_environment(slot_name: str | None = None) -> str:
    """
    Garante que a estrutura mínima do projeto exista antes de subir o app.

    Responsabilidades:
    - garantir a raiz de slots
    - normalizar/criar o slots_meta.json
    - garantir a pasta do slot ativo
    """
    ensure_slots_root_dir()
    load_slots_meta()

    active_slot = slot_name or get_active_slot_name()
    ensure_slot_dir(active_slot)

    return active_slot


def build_default_context(slot_name: str | None = None) -> ScraperContext:
    """
    Monta o contexto padrão da aplicação já apontando para o slot ativo.
    """
    active_slot = prepare_environment(slot_name)
    context = build_context(slot_name=active_slot)

    # Garante também toda a árvore de pastas do contexto atual.
    build_context_paths(context, ensure=True)

    return context


def build_app(
    slot_name: str | None = None,
    *,
    auto_load_summary: bool = True,
) -> ScraperApp:
    """
    Instancia a aplicação principal já pronta para uso no painel.
    """
    context = build_default_context(slot_name)

    return ScraperApp(
        context=context,
        auto_load_summary=auto_load_summary,
    )


def main() -> None:
    load_windows_user_environment()
    app = build_app()
    serve(app)


if __name__ == "__main__":
    main()
