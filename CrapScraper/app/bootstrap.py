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
    from app.update_retry_live_objective import install_update_retry_live_objective
    from app.addition_runtime_recovery import install_addition_runtime_recovery
    from app.addition_decision_sync import install_addition_decision_sync
    from app.addition_execution_recovery import install_addition_execution_recovery
    from app.additions.chatgpt_playwright_runtime import install_addition_chatgpt_playwright
    from app.additions.chatgpt_background_route_recovery import install as install_chatgpt_background_route_recovery
    from app.additions.catalog_taxonomy_runtime import install_catalog_taxonomy_contract
    from app.comparison_live_reconciliation import install_comparison_live_reconciliation
    from app.plugintheme_access_fallback import install_plugintheme_access_fallback

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

    # Antes de um retry de atualização, reconcilia a versão atual do WooCommerce
    # e a versão viva da mesma fonte aprovada. Isso impede que snapshots antigos
    # bloqueiem a nova tentativa quando a origem avançou após a aprovação.
    install_update_retry_live_objective()

    # Quando o check-access do PluginTheme responde falso, ainda permitimos uma
    # única prova no endpoint de arquivo. Só há sucesso se o retorno final for um
    # ZIP válido ou uma URL assinada válida; autenticação real continua obrigatória.
    install_plugintheme_access_fallback()

    # A fila de adição sincroniza aprovações automaticamente. Primeiro instalamos
    # as recuperações legadas; em seguida o runtime Playwright assume conteúdo e
    # imagem para que ambos sejam gerados no projeto [CS] Automação do ChatGPT.
    install_addition_runtime_recovery()
    install_addition_decision_sync()
    install_addition_execution_recovery()
    install_addition_chatgpt_playwright()

    # O ChatGPT muda a composição das rotas/projetos com frequência. Esta camada
    # roda por último sobre o Playwright e recupera o projeto pelo token g-p-* se
    # uma conversa salva deixar de abrir no navegador em segundo plano.
    install_chatgpt_background_route_recovery()

    # Durante esta fase do cadastro, a taxonomia é propositalmente mínima:
    # exatamente uma categoria (Plugin ou Tema) e nenhuma tag. O contrato é
    # aplicado no payload final, inclusive em retries de jobs preparados antes.
    install_catalog_taxonomy_contract()

    # Um catálogo PluginTema é um snapshot. Para linhas marcadas como produto novo,
    # o resultado visível é reconciliado com o WooCommerce ao vivo antes de permitir
    # que uma aprovação de cadastro novo continue ativa.
    install_comparison_live_reconciliation()

    # Import the domain graph only after load_settings has published the
    # canonical SCRAPER_DATA_DIR. The migrated collection core resolves its
    # legacy-compatible paths at import time.
    from app.web.api import ApplicationServices

    runtime = JsonStore(settings.data_dir / "consolidated_runtime.json")
    return Application(settings, ApplicationServices.build(settings, runtime))
