from __future__ import annotations

import os
import sys
from pathlib import Path

from app.bootstrap import create_application
from app.configuration import WINDOWS_USER_ENVIRONMENT_KEYS


CURRENT_APP_DEFAULTS = {
    "SCRAPER_STORE_WRITE_ENABLED": "1",
    "SCRAPER_ADDITION_EXECUTION_ENABLED": "1",
    "SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED": "1",
}


def load_windows_user_environment() -> dict[str, bool]:
    """Carrega a configuração persistida do usuário sem registrar valores."""
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


def apply_current_app_defaults() -> None:
    """Aplica defaults somente quando shell e registro do Windows não definiram o valor."""
    for key, value in CURRENT_APP_DEFAULTS.items():
        os.environ.setdefault(key, value)


def main() -> None:
    load_windows_user_environment()
    apply_current_app_defaults()
    print(f"[CrapScraper] Aplicação modular atual: {Path(__file__).resolve()}", flush=True)
    create_application().serve()


if __name__ == "__main__":
    main()
