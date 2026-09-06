# Auditoria Atualizar / Adicionar — 2026-09-06

Base remota verificada por `git fetch origin`: `106215f25539f3d3d2b1a70fb5f05ef91e7298cf`.
Checkout inicial limpo, main local `15fec5e`, 31 commits atrás. Branch de trabalho:
`fix/modular-flow-audit-agricola`. Somente arquivos dentro de CrapScraper/ serão alterados.

## Proprietários observados antes de editar

| Etapa | Proprietário modular e entrada |
|---|---|
| Launcher / identidade | `Abrir CrapScraper.bat` → `main.py` → `app/bootstrap.py:create_application` → `app/web/server.py`; `/api/health` em `app/web/routes.py` |
| Comparar / aprovação | `static/js/compare.js` → `/api/comparison/run`, `/decision`, `/decisions/bulk` → `comparison/service.py:ComparisonService`, `matching.py`, `decisions.py`; SQLite preserva decisão e histórico |
| Materializar Atualizar | `/api/updates/materialize` → `updates/service.py:UpdateService.materialize` → `UpdateRepository.materialize`; identidade única por comparison_item_id, nova versão pode reabrir job |
| Elegibilidade Atualizar | `UpdateService._execution`, `_require_job_execution`; `current_app_recovery.py:_prepare_job_execution` valida ambiente e fonte |
| Execução individual | `static/js/update.js` é quem envia `/api/updates/execute` ou `/retry`; `update-individual-feedback.js` também modifica o botão na fase de captura |
| Fila / pausa / cancelamento | `/api/updates/batch/{start,pause,resume,cancel}` → `UpdateBatchService`; posição/resultados/lock distinguem ativo e pendentes; `update_queue_state_runtime.py` projeta esses dados no backend |
| Retry / objetivo vivo | `update_retry_live_objective.py:_refresh_retry_objective`, `current_app_recovery.py:patched_retry`; fila atualmente chama executor diretamente |
| Transação Atualizar | `updates/executor.py:UpdateExecutor.execute`: autorização, leitura fresca Woo, preflight destino, autenticação e versão da fonte, download, validação ZIP, backup+SHA, instalação, SHA remoto, PUT pt_versao, GET de confirmação e SHA final |
| Adaptadores transacionais | `updates/sources.py:SourceRegistry`, recuperações de fonte; `updates/adapters.py`, `target_preflight.py`, `fast_transaction.py`; backup/rollback/SSH/helper permanecem responsáveis pelos arquivos |
| Conclusão Atualizar | `UpdateRepository.finish` + `updates/history.py` outbox WordPress; `update_completion_and_retry_runtime.py` consome fila da aprovação e projeta Atualizado no Comparar |
| Materializar Adicionar | `/api/additions/materialize` → `AdditionService` → `AdditionRepository`; `addition_decision_sync.py` sincroniza aprovação e mudanças de dados, sem duplicar job |
| Executar Adicionar | `static/js/add.js` → `/api/additions/execute`, `/retry`, `/batch/*` → `AdditionService`, `AdditionBatchService`, `AdditionExecutor` |
| Fonte / ZIP Adicionar | `additions/source.py:ProductResearchService`, `AdditionSourceService`, `source_preflight_runtime.py`; executor confirma developer/official_url, fonte imutável e versão, baixa ZIP e revalida cache SHA |
| Descrição ChatGPT | `ChatGPTContentService.generate` ligado pelo bootstrap a `chatgpt_content_response_runtime.py:generate_content`; `_wait_content_response` lê DOM, parser em `chatgpt_json_recovery_runtime.py`, `strict_job_identity_runtime.py` valida identidade, `product_content_contract_runtime.py` aplica contrato comercial |
| Conversa / restart | `strict_job_identity_runtime.py`, `chatgpt_new_job_project_runtime.py`, `chatgpt_job_cache_recovery_runtime.py`; JSON de estado por job e URL/cache em SQLite; executor persiste após cada artefato |
| Imagem | `ImageService.generate` → `chatgpt_playwright_image.py`: CSIMG único, imagens anteriores, ordem DOM, bytes novos/estáveis, conclusão do turno, arquivo normalizado e fingerprint por job |
| Criar WooCommerce | `AdditionExecutor` → `ArtifactPublisher` publica ZIP, `AdditionStoreGateway` reconcilia pelo job, envia mídia, cria pai variável draft, variações Anual/Vitalício, publica e valida; `woocommerce_bridge_runtime.py` e contratos de taxonomia/preço complementam gateway |
| Ordenação Adicionar | `addition_sort_runtime.py` coleta resultado filtrado, ordena e pagina; `add-sort-controls.js` injeta controles e intercepta fetch global |
| Composição real | `app/bootstrap.py` instala runtimes antes de construir `ApplicationServices`; testar só classes sem essa composição não demonstra comportamento da aplicação atual |

## Evidências e causas

- Diagnóstico `chatgpt-20260906-141219.json` e PNG lidos. Resposta Agricola completa, quebra literal antes da aspa final de official_url, classificada como `content_response_timeout`.
- Main remota já repara esse controle, mas escolhe o último objeto sem verificar schema/produto. O scanner também considera aspas no Markdown anterior como início de string JSON. O parser base ainda inventa product_name ausente usando o job.
- Leitor diferencia respostas por texto, não por turno único da solicitação; diagnóstico usa sempre timeout. Resposta pronta tolera Stop obsoleto após estabilidade, comportamento a preservar.
- Recuperação promove URL SQLite a conversa isolada quando estado anterior está ausente, sem prova persistida da identidade. Cache de imagem compara fingerprint, mas não confere SHA dos bytes no reuso.
- Spinner é inserido pelo script auxiliar e apagado pelo proprietário do POST. Polling substitui botões durante request e perde o bloqueio associado ao elemento antigo.
- Retry individual reconcilia objetivo; worker do lote chama diretamente executor. A reconciliação pode limpar erro não recuperável ao avançar objetivo se não houver gate anterior.
- Consumo de aprovação escreve site_version, mas mantém source_version antiga após drift. Overlay pode deixar de reconhecer versão efetivamente concluída.
- Fila já possui pendentes reais no backend; os cards auxiliares fazem GET redundante. Contadores e linhas podem ser projetados de snapshots distintos.
- Ordenação de Adicionar existe, porém labels de nome não mudam e mudança do sort não reinicia paginação; fetch global cria proprietário paralelo.
- Baseline `python -m pytest -q tests`: 391 passed, 31 failed. Falhas preexistentes serão investigadas, incluindo contratos antigos, isolamento entre testes e diferenças Windows/POSIX.

## Estratégia

Corrigir os proprietários acima, remover interceptações de UI substituídas por comportamento canônico, manter preflight/transação/isolamento fail-closed. Testar primeiro diagnóstico real e casos adversariais; depois regressão completa, bootstrap e E2E em dados temporários. Testes reais de escrita ficam no roteiro para o operador após entrega.

## Fechamento da validação local

- Python completo: 482 passed, 2 skipped (integrações POSIX reservadas ao Linux da CI).
- Bootstrap em processo novo: passou com execução individual, retry, dois produtos no lote, um ativo e outro enfileirado, rejeição de retry do enfileirado, consumo da aprovação e proveniência Agricola após reinício.
- Compileall e syntax checker: passaram; node --check passou nos 41 JS/MJS.
- Os 12 E2Es de run_ui.mjs terminaram individualmente com exit code 0, incluindo limpeza. Execução individual: executeCalls=1, retryCalls=1, batchStartCalls=1. DOM Agricola: três layouts, imagem isolada e turno desconhecido rejeitado.
- E2Es antigos foram adaptados aos modais atuais, seis cards de Atualizar e fixtures com contexto e aprovações persistidas. As verificações de paginação, download, fechamento de modais e payloads foram preservadas.
- Comparar descartava mudanças de filtro durante uma requisição. Agora agenda a consulta com os filtros mais recentes; compare_ui e compare_loading_ui comprovam a correção.
- Testes de arquitetura acompanham a composição modular atual; isolamento de adapters entre testes é complementado pelo bootstrap real em subprocesso. Não foram removidos gates transacionais para obter passes.
- Scripts temporários e relatórios intermediários foram removidos de .runtime; PID e logs da aplicação local permanecem ignorados pelo Git.

Teste real após merge, usando Abrir CrapScraper.bat e porta 8766: atualizar um produto com um clique; executar lote e observar Preparados → Na fila → Em andamento → Concluído; retry individual; conferir Atualizado em Comparar; adicionar Agricola; verificar descrição e imagem; adicionar outro produto e confirmar que conteúdo/imagem não foram misturados. Os E2Es usam dados locais e não substituem esse teste real de publicação.
