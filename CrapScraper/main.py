from __future__ import annotations

import os
import sys

from app.bootstrap import create_application
from app.configuration import WINDOWS_USER_ENVIRONMENT_KEYS


def load_windows_user_environment() -> dict[str, bool]:
    """Carrega a configuração persistida do usuário sem registrar valores."""
    presence={key:bool(os.getenv(key,"").strip()) for key in WINDOWS_USER_ENVIRONMENT_KEYS}
    if sys.platform!="win32":return presence
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,"Environment") as environment:
            for key in WINDOWS_USER_ENVIRONMENT_KEYS:
                if presence[key]:continue
                try:value,_kind=winreg.QueryValueEx(environment,key)
                except FileNotFoundError:continue
                normalized=str(value or "").strip()
                if normalized:os.environ[key]=normalized;presence[key]=True
    except OSError:pass
    return presence


def main() -> None:
    load_windows_user_environment()
    create_application().serve()


if __name__ == "__main__":
    main()
