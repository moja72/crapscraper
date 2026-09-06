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
    from app.update_completion_and_retry_runtime import install_update_completion_and_retry_runtime
    from app.update_queue_state_runtime import install_update_queue_state_runtime
    from app.addition_runtime_recovery import install_addition_runtime_recovery
    from app.addition_decision_sync import install_addition_decision_sync
    from app.addition_execution_recovery import install_addition_execution_recovery
    from app.addition_sort_runtime import install_addition_sort_runtime
    from app.additions.chatgpt_playwright_runtime import install_addition_chatgpt_playwright
    from app.additions.chatgpt_background_route_recovery import install as install_chatgpt_background_route_recovery
    from app.additions.chatgpt_product_isolation_runtime import install as install_chatgpt_product_isolation
    from app.additions.product_content_contract_runtime import install as install_product_content_contract
    from app.additions.strict_job_identity_runtime import install as install_strict_job_identity
    from app.additions.chatgpt_new_job_project_runtime import install as install_chatgpt_new_job_project_runtime
    from app.additions.chatgpt_job_cache_recovery_runtime import install_chatgpt_job_cache_recovery_runtime
    from app.additions.chatgpt_json_recovery_runtime import install_chatgpt_json_recovery_runtime
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

    # Corrige o caminho individual sem tocar no proprietário da execução em lote:
    # drift de versão vira retry recuperável, conclusão consome a aprovação
    # operacional e a Comparação passa a projetar imediatamente "Atualizado".
    install_update_completion_and_retry_runtime()

    # Projeta separadamente os produtos que já foram enviados para o lote, mas
    # ainda aguardam sua vez. O estado real do executor continua transacional.
    install_update_queue_state_runtime()

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
    # recupera o projeto pelo token g-p-* se uma conversa salva deixar de abrir.
    install_chatgpt_background_route_recovery()

    # Cada produto passa a ter uma conversa própria dentro do projeto. Isso evita
    # que imagens de 911, 69 Clothing ou qualquer item anterior sejam elegíveis
    # para outro cadastro. A captura ainda exige que a imagem pertença ao turno
    # exato que respondeu ao prompt atual.
    install_chatgpt_product_isolation()

    # O conteúdo segue o padrão comercial de referência do Elementor Pro, mantém
    # nome imutável e invalida descrições antigas fora desse contrato.
    install_product_content_contract()

    # Guard final de identidade: vincula a automação ao job/produto/fonte exatos,
    # exige chat novo e vazio por item e rejeita qualquer resposta cujo nome não
    # seja exatamente o produto da linha atual. Cache antigo é invalidado.
    install_strict_job_identity()

    # Para um produto NOVO, não tente reabrir a conversa concreta antiga antes de
    # criar o chat. O token g-p-* é a identidade durável: abrimos diretamente a
    # raiz do projeto e criamos um chat vazio. Assim uma /c/ antiga ou instável não
    # bloqueia o cadastro seguinte em generating_description.
    install_chatgpt_new_job_project_runtime()

    # Retry/restart da Adição reconstrói a proveniência do chat a partir do mesmo
    # job persistido em SQLite. Isso permite terminar a imagem do produto correto
    # sem cair num chat de outro item e torna a prova de chat vazio fail-closed.
    install_chatgpt_job_cache_recovery_runtime()

    # O DOM do ChatGPT pode inserir quebras de linha dentro de strings visualmente
    # renderizadas (o diagnóstico real fez isso no official_url). Extraia o último
    # objeto JSON balanceado e repare apenas formatação segura, nunca truncamento.
    install_chatgpt_json_recovery_runtime()

    # Ordenação da fila de Adicionar usa o mesmo contrato visual de Atualizar.
    install_addition_sort_runtime()

    # Taxonomia fixa do catálogo PluginTema: Plugin #504 ou Tema #525, nunca ambas,
    # e nenhuma tag. Os IDs são enviados diretamente sem criar termos novos.
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