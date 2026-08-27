from __future__ import annotations

from app.configuration import load_settings
from app.core.persistence import JsonStore
from app.web.server import Application


def create_application() -> Application:
    settings = load_settings()
    # Import the domain graph only after load_settings has published the
    # canonical SCRAPER_DATA_DIR.  The migrated collection core resolves its
    # legacy-compatible paths at import time.
    from app.web.api import ApplicationServices

    runtime = JsonStore(settings.data_dir / "consolidated_runtime.json")
    return Application(settings, ApplicationServices.build(settings, runtime))
