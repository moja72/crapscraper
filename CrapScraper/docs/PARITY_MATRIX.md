# Matriz de paridade funcional

Auditoria iniciada em 2026-08-27 sobre a branch `homologation/crapscraper-final`, após o commit `440ecc9`.

Critério: somente recursos alcançáveis pelos entrypoints carregados (`app/web.py` no legado e `app/web/routes.py` no consolidado), com implementação e/ou testes operacionais. Policies e assets não instalados não contam como funcionalidade.

| Área | Estado antes da Fase 8 | Evidência e lacuna confirmada |
|---|---|---|
| Coleta multi-run e locks de conta | AUSENTE | O legado carregava `ScraperRunManager`; o consolidado instanciava um único `CollectionEngine/ScraperApp`. O núcleo migrado ainda contém o manager funcional. |
| Fila encadeada de coletas | AUSENTE | Manager e persistência `fila.json` existem no núcleo migrado, mas não estavam expostos por serviço, rota ou UI. |
| Opções avançadas da coleta | PARCIAL | `verify_mode`, `save_every_items` e `save_every_minutes` são consumidos e persistidos pelo núcleo; faltavam controles e salvamento no consolidado. |
| Slots e contextos | PARCIAL | Criar, selecionar, definir padrão, limpar e excluir estavam presentes. Renomear, remover contexto e remover zerados existiam no núcleo carregado, mas não eram expostos. |
| Central de catálogos/exportação | PARCIAL | Catálogos são consumidos por comparação/sync; busca, preview, exportação, geração PluginTema e administração completa do legado não estão expostos. |
| Comparação avançada | PARCIAL | Busca, paginação, decisões e vínculo manual presentes. Filtros numéricos, massa, restauração, log e cache/restauração de resultado não estão completos. |
| Listas nomeadas de atualização | AUSENTE | Jobs SQLite persistem; o controlador atual possui apenas um lote em memória e nenhuma lista ativa persistente. |
| Preparação/plano de atualização | PARCIAL | Há módulos `preparation.py` e pipeline seguro, mas serviço/UI saltam da aprovação para execução e não expõem plano não destrutivo em massa. |
| Histórico/logs de atualização | PARCIAL | Tentativas por job, erro e estágio presentes; falta central global, exportação, limpeza controlada e ações de log. |
| Persistência de lotes Update/Add | PARCIAL | Jobs e tentativas persistem; posição, pausa, checkpoint e recuperação do controlador de lote ficam em memória. |
| Monitor WordPress manual | PARCIAL | HMAC, enable/disable, histórico e polling presentes. A resolução dinâmica antes de `no_match` ainda falta. |
| Adicionar: browser/API/paralelismo | PARCIAL | API OpenAI e fluxo canônico presentes; automação ChatGPT por navegador, geração paralela e reaproveitamento granular do legado não estão expostos. |
| Resolução oficial/developer | PARCIAL | Resolução básica e regra de não inventar existem. Marketplaces, similaridade, bloqueios e rejeição ampla de redistribuidores ainda são incompletos. |
| Loja/preços | PARCIAL | Resumo performático, qualidade incremental, preview/apply gated, packs e filtro por produto presentes. Falta editor por linha e feedback completo de salvar um/todos. |
| Central global de processos/créditos | AUSENTE | O legado carregava agregadores de processos/histórico; o consolidado mantém estados por aba. Créditos só aparecem em diagnósticos de erro, sem fonte confiável de saldo global. |
| Desempenho/Servidor/Armazenamento/Cron | NÃO COMPROVADO | Histórico contém otimizações internas e integração SSH, mas nenhuma aba/rota carregada de PSI, Lighthouse, Netdata, monitor de servidor, disco ou cron foi encontrada. Não migrar sem nova evidência. |

## Itens apontados incorretamente como totalmente ausentes

- Opções avançadas de coleta já existiam no modelo, engine e persistência; faltava exposição.
- Administração básica de slots já existia.
- Preparação de Update e Addition já possuía módulos e estados, mas não uma jornada completa na UI/API.
- Loja já possuía preview/aplicação gated para preços e packs; falta granularidade operacional.
- Histórico individual e persistência dos jobs de Update/Addition já estavam presentes.
- HMAC e monitor manual já estavam presentes e testados.

## Novas lacunas confirmadas

- A rota consolidada de categorias Woo não paginava além de 100; corrigida na Fase 7.
- O catálogo completo de coleta estava acessível apenas como contagem, sem endpoint de leitura/exportação.
- A identidade de execução (`run_id`) não fazia parte do contrato consolidado de coleta, impedindo controle isolado mesmo com o manager já migrado.
- A UI não indicava quando uma análise global de qualidade ainda estava em andamento; corrigido na Fase 7.

## Fases finais

1. Fase 8: manager multi-run, locks, encadeamento, opções avançadas e administração de slots/contextos.
2. Fase 9: central de catálogos/exportações e comparação avançada.
3. Fase 10: preparação, listas, lotes persistentes, histórico e monitor manual de Update.
4. Fase 11: Addition persistente, modos browser/API, paralelismo e resolução oficial.
5. Fase 12: central global de processos, histórico, créditos confiáveis e indicadores.
6. Fase 13: somente recursos adicionais cuja integração histórica seja comprovada.

## Estado após as Fases 8 e 9

| Área | Estado atual | Evidência |
|---|---|---|
| Coleta multi-run, fila, opções e contextos | PRESENTE | Manager multi-run, isolamento por `run_id`, locks, fila persistida, configuração avançada e administração de contextos expostos e cobertos por E2E. |
| Central de catálogos | PRESENTE | Visão administrativa canônica com busca, paginação, metadados, contexto, prévia paginada, carregamento na Coleta e download CSV. Ações destrutivas continuam centralizadas e confirmadas na Coleta, sem duplicação. |
| Geração PluginTema | PRESENTE | Geração assíncrona local a partir de leitura WooCommerce, com estado/log, filtro de tipos, CSV atômico e zero escrita WooCommerce. |
| Comparação avançada | PRESENTE | Seleção de página/global filtrada, seleção persistente entre páginas, massa, filtros de candidatos/score, reset, histórico, vínculo/rejeição, diagnóstico, log, duração e cache por assinatura. |
| Cache do último resultado | PRESENTE (sessão) | O legado comprovado mantinha cache em memória por assinatura dos dois CSVs, não persistência entre processos. O consolidado preserva essa semântica, identifica reutilização e invalida quando tamanho/mtime muda. |

### Decisões de migração da Fase 9

- A administração destrutiva de slots/contextos não foi duplicada na central: continua na aba Coletar usando o mesmo repositório e confirmações já homologadas.
- O refresh incremental avançado PluginTema baseado em policies não foi copiado. A função utilizável foi restaurada como geração assíncrona canônica, somente leitura no WooCommerce e escrita atômica de um novo CSV local.
- Não foi criada persistência de payload completo da comparação entre restarts porque o legado carregado usava cache em memória por assinatura; persistir resultados antigos mudaria essa semântica e aumentaria o risco de apresentar dados obsoletos.
