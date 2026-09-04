from __future__ import annotations

from app.configuration import load_settings
from app.core.persistence import JsonStore
from app.web.server import Application


def create_application() -> Application:
    settings = load_settings()
    # A pasta CrapScraper/ é a aplicação modular atual. Instala as correções
    # sobre este grafo antes de construir os serviços; a raiz do repositório
    # continua apenas como legado e não é usada pelo launcher atual.
    from app.missing_target_recovery import install_missing_target_recovery
    from app.helper_diagnostic import install_helper_diagnostic
    from app.current_app_recovery import install_current_app_recovery
    from app.update_runtime_consistency import install_update_runtime_consistency
    from app.legacy_permission_recovery import install_legacy_permission_recovery

    install_missing_target_recovery()
    install_helper_diagnostic()

    # update_runtime_consistency acrescenta overlay de versão/origem e download
    # binário. current_app_recovery precisa ser instalado DEPOIS para que o retry
    # final sempre faça a revalidação real da fonte, em vez de confiar apenas no
    # selo de ambiente em cache.
    install_update_runtime_consistency()
    install_current_app_recovery()

    # Envolve o backup SFTP já finalizado pelas políticas anteriores e só atua no
    # caso específico de EACCES causado por ZIPs legados com owner/mode antigos.
    install_legacy_permission_recovery()

    # Import the domain graph only after load_settings has published the
    # canonical SCRAPER_DATA_DIR. The migrated collection core resolves its
    # legacy-compatible paths at import time.
    from app.web.api import ApplicationServices

    runtime = JsonStore(settings.data_dir / "consolidated_runtime.json")
    return Application(settings, ApplicationServices.build(settings, runtime))
