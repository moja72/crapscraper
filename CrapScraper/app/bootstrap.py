from __future__ import annotations

from app.configuration import load_settings
from app.core.persistence import JsonStore
from app.web.api import ApplicationServices
from app.web.server import Application


def create_application() -> Application:
    settings = load_settings()
    runtime = JsonStore(settings.data_dir / "consolidated_runtime.json")
    return Application(settings, ApplicationServices.build(settings, runtime))
