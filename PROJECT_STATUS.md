# PROJECT_STATUS — diagnóstico do CrapScraper

Diagnóstico iniciado em 11/08/2026, por inspeção estática, consultas SQLite em modo somente leitura e validações de sintaxe. A reorganização estrutural posterior moveu os assets citados nas seções históricas de `app/panel.js` e `app/panel.css` para `app/static/panel.js` e `app/static/panel.css`, sem alterar suas linhas ou comportamento. Os caminhos e linhas são aproximados. “Confirmado” significa comprovado pelo código/dados locais; “hipótese” e “depende de teste visual” são marcados explicitamente.

## 1. Objetivo do projeto

O CrapScraper coleta catálogos de produtos por contexto (site, tipo de item, conta e slot), persiste os resultados em CSV/JSON e oferece um painel HTTP local para operar as coletas. A camada de comparação cruza um catálogo UltrapackV2 (origem) com uma planilha PluginTema (destino), identifica correspondências e diferenças de versão, sugere candidatos aproximados e registra decisões e vínculos manuais em SQLite.

Evidência: `main.py:12-65` monta o contexto e inicia `app.web.serve`; `app/engine.py:5342-5785` contém o fluxo assíncrono/principal de coleta; `app/comparison.py:1192-2673` constrói a comparação completa; `app/web.py:2942-3205` expõe fontes, pesquisa e dados da comparação.

## 2. Arquitetura e principais arquivos

- `main.py:12-65`: entrada; prepara slots, cria `ScraperApp` e sobe o servidor. Importante: `prepare_environment()` cria/normaliza estrutura, portanto iniciar o app não é estritamente somente leitura.
- `app/settings.py:15-58`: caminhos centrais; assets ativos são `app/static/panel.css` e `app/static/panel.js`; importações em `data/imports`; decisões em `data/comparison_decisions.sqlite3`.
- `app/models.py:122-1206`: modelos de slot, contexto, opções, categoria, item de catálogo, contadores e snapshot de estado.
- `app/adapters.py:183-847`: regras e seletores por site/tipo, incluindo adaptadores Ultrapack e PluginTema.
- `app/browser.py:294-1517`: sessão Playwright, navegação, autenticação e controles de pausa/parada.
- `app/engine.py:468-5785`: HTTP autenticado, parsing, categorias, paginação, detalhes, filas e execução do scraper.
- `app/storage.py:209-3273`: paths, slots, leitura/escrita atômica, catálogo, progresso, caches, configurações, logs e limpeza. Não armazena as decisões de comparação.
- `app/app.py:406-2092`: estado, controle, `ScraperApp` e gerência de múltiplas execuções.
- `app/comparison.py:1-3240`: normalização, matching, versões, candidatos, métricas, filtros/paginação e pesquisa de produtos.
- `app/comparison_decisions.py:13-797`: decisões operacionais e relacionamentos persistidos em SQLite.
- `app/web.py:413-1704`: HTML está embutido em string Python; não foram encontrados templates HTML separados ativos. Rotas ficam aproximadamente em `2942-3479`.
- `app/static/panel.js:3188-4620`: carregamento/renderização da comparação, decisões, candidatos e vínculo manual.
- `app/static/panel.css:1215-1664` e `2000-2247`: layout da comparação, tabela, controles e modal.

O arquivo histórico agora preservado em `docs/legacy/leia-me.txt` descreve uma arquitetura futura dividida em subpacotes, mas essa árvore não existe no estado atual. A documentação principal foi substituída por `README.md` e `PROJECT_STRUCTURE.md`.

## 3. Fluxo atual da comparação

1. O painel chama `GET /comparacao/fontes` (`app/panel.js:3188-3230`; `app/web.py:2942-2952`) e recebe catálogos salvos/importados construídos por `_build_comparison_sources_payload()` (`app/web.py:2342+`).
2. Ao executar/filtrar, `refreshComparison()` (`app/panel.js:4269-4343`) chama `GET /comparacao/data` com IDs, filtros, paginação e `force`.
3. A rota resolve os arquivos e chama `build_comparison_payload()` (`app/web.py:3019-3205`).
4. `_build_full_comparison()` (`app/comparison.py:1192-2673`) normaliza CSVs, cria índices únicos por URL/nome e carrega vínculos do SQLite.
5. Para cada produto PluginTema, aplica nesta ordem: vínculo `manual_confirmed`; match seguro por URL oficial; match seguro por nome normalizado; candidatos aproximados. Rejeições manuais excluem chaves sugeridas (`app/comparison.py:1323-1594`).
6. Sem par, gera `site_only`; fontes não usadas viram `new_source` (`app/comparison.py:1601-1960`). Pares passam pela classificação de versão em `_matched_row()` (`app/comparison.py:1062-1189`).
7. O payload agrega métricas, decisões, filtros e paginação (`app/comparison.py:2080-3080`), e `renderComparison()` cria 11 células por linha (`app/panel.js:3588-4110`).

Confirmado: há cache em memória indexado somente pelas assinaturas dos dois arquivos (`app/comparison.py:2676-2699`), não pela data/revisão do SQLite. O salvamento via painel força recomparação (`app/panel.js:3288-3291`), mas uma alteração externa no banco pode permanecer invisível enquanto os CSVs não mudarem. Correção recomendada: incluir revisão/mtime do banco na chave ou invalidar explicitamente o cache após qualquer mutação.

## 4. Estados de comparação encontrados no código

Estados de situação realmente classificados em `_STATUS_ORDER`/`_STATUS_LABELS` (`app/comparison.py:26-46`):

- `update_available`: origem mais nova.
- `version_review`: comparação inconclusiva/versão suspeita.
- `site_version_missing`: versão ausente no PluginTema.
- `source_version_missing`: versão ausente no Ultrapack.
- `site_ahead`: PluginTema aparentemente mais novo.
- `updated`: versões equivalentes.
- `site_only`: somente PluginTema.
- `new_source`: somente Ultrapack.

Estados de relacionamento aceitos por `RELATIONSHIP_LABELS` (`app/comparison_decisions.py:34-41`): `safe_auto`, `candidate`, `manual_confirmed`, `manual_rejected`, `confirmed_not_in_source`, `pending_review`.

Decisões operacionais são um eixo separado (`app/comparison_decisions.py:13-31`): `pending`, `approve_update`, `ignore`, `review_later`, `same_product`, `different_products`, `approve_new_product`. Não confundir `manual_confirmed`/`manual_rejected` com estas decisões.

Confirmado: `safe_auto` e `pending_review` aparecem no payload; `candidate` descreve sugestões, mas não é gravado automaticamente como uma linha de relacionamento; `manual_confirmed`, `manual_rejected` e `confirmed_not_in_source` já existem no banco local.

## 5. Funcionalidades comprovadamente implementadas

- Normalização e leitura dos dois formatos de catálogo, incluindo chaves estáveis de produto (`app/comparison.py`, funções `_normalize_source_rows` e `_normalize_site_rows`).
- Match automático por URL oficial e nome normalizado, com unicidade e prevenção de reutilização da mesma origem (`app/comparison.py:1203-1488`).
- Geração e pontuação de até três candidatos aproximados, corte mínimo 45 e sinalização de candidatos disputados (`app/comparison.py:1491-1599`, `2361-2485`).
- Classificação dos oito estados de situação e diagnóstico de qualidade de versões (`app/comparison.py:26-46`, aproximadamente `900-1058`).
- Pesquisa paginada/filtrada e métricas no backend e no frontend (`app/comparison.py:2700-3080`; `app/panel.js:3588-4343`).
- Decisões individuais e em lote com histórico SQLite (`app/comparison_decisions.py:180-450`; rotas em `app/web.py:3376-3479`).
- Persistência de vínculos e rejeições, com exclusividade de `manual_confirmed` nos dois lados (`app/comparison_decisions.py:511-686`).
- Reaplicação de vínculos confirmados e exclusão de candidatos rejeitados na recomparação (`app/comparison.py:1323-1594`).
- Pesquisa de produtos do catálogo oposto (`search_comparison_catalog_products`, `app/comparison.py:3082-3229`; rota `app/web.py:2954-3017`).
- Contagem HTML coerente: cabeçalho com 11 `<th>`, placeholder com `colspan="11"` (`app/web.py:1559-1583`) e linhas renderizadas com 11 `<td>` (`app/panel.js:4028-4110`).
- Sintaxe válida em todos os módulos Python ativos e em `app/panel.js` (`node --check` sem erros).
- SQLite íntegro (`PRAGMA integrity_check = ok`) e com registros reais: 1 `manual_confirmed`, 1 `manual_rejected`, 1 `confirmed_not_in_source`.

## 6. Funcionalidades parcialmente implementadas

- Modal de vínculo: HTML e CSS existem (`app/web.py:1621-1701`; `app/panel.css:2040-2161`), mas não há controlador JavaScript.
- Vínculo com “outro produto”: existe e pode funcionar inline dentro de `<details>` (`app/panel.js:3899-3942`, `4496-4618`), porém não segue o fluxo de pop-up planejado.
- “Ver outros”: botão existe (`app/panel.js:3980-3986`), mas só abre/rola o diagnóstico (`4473-4492`), sem abrir modal nem iniciar busca.
- Rejeição manual: funciona para candidatos sugeridos (`app/panel.js:3358-3432`), mas não há ação equivalente visível para resultados arbitrários da pesquisa manual.
- `confirmed_not_in_source` e `pending_review`: backend aceita, porém não foi localizado controle direto correspondente no fluxo atual do modal/linha; há evidência de `confirmed_not_in_source` inserido anteriormente no SQLite.
- Cache da comparação: correto para mudanças nos arquivos, incompleto para mudanças externas no banco.
- Responsividade da tabela: há rolagem horizontal e largura fixa, mas a experiência exige 1800 px e 11 colunas, inclusive uma coluna exclusiva de seleção.

## 7. Funcionalidades ainda ausentes

- Funções `open/close/render` do modal, estado do item ativo, foco, Escape, clique no backdrop e eventos para `comparison_link_modal_*`.
- Conexão do botão “Ver outros” ao modal.
- Renderização das sugestões e dos resultados dentro de `#comparison_link_modal_suggestions` e `#comparison_link_modal_results`.
- Rejeição de um vínculo escolhido pela pesquisa geral, se esse comportamento fizer parte do requisito.
- Testes automatizados localizados para matching, versões, rotas, cache e decisões. Não foi encontrada suíte de testes no inventário.
- Migrations versionadas do SQLite. O “schema migration” atual é apenas `CREATE TABLE/INDEX IF NOT EXISTS` em `initialize_database()` (`app/comparison_decisions.py:97-177`), incapaz de alterar esquemas já existentes.
- Etapas operacionais de download/upload/cadastro: o próprio HTML informa que ainda serão adicionadas (`app/web.py:1589-1615`).

## 8. Diagnóstico do cabeçalho espremido

### Evidência confirmada

- A tabela tem 11 colunas (`app/web.py:1559-1574`), incluindo checkbox em coluna própria (`1561-1563` e `app/panel.js:4029-4036`). A intenção futura de incorporá-lo a “Situação” ainda não foi aplicada.
- Há três gerações sobrepostas de regras para `.comparison-table`: base com `width:100%; min-width:1120px` (`app/panel.css:1235-1240`), sobrescrita com `table-layout:fixed; min-width:1420px` (`2029-2038`) e regra final `width/min-width:1800px; table-layout:fixed` (`2164-2168`). A cascata final deveria vencer, mas a duplicação dificulta prever versões antigas/em cache.
- Os cabeçalhos permitem quebra (`white-space: normal`, `2176-2179`) e usam fonte de 11 px, caixa alta e espaçamento de letras (`1250-1260`). Títulos como “Ação recomendada” quebram em larguras fixas de 190 px; “Correspondência” recebe 160 px.
- As 11 larguras declaradas em `:nth-child` (`2181-2237`) somam 1.726 px; a tabela é 1.800 px. A distribuição é funcional, mas concentra informação complexa em células de 130–190 px.
- O wrapper permite rolagem horizontal (`1227-1233`, reforçado em `2022-2027`), e os contêineres externos são limitados a 100% (`2005-2013`). Portanto a tabela não deveria ser comprimida ao viewport se a folha final estiver carregada.
- CSS anterior usa `overflow-wrap:anywhere` (`2034-2038`), mas a regra final posterior volta para `overflow-wrap:normal` (`2170-2174`). Se o navegador estiver recebendo uma versão incompleta/antiga do asset, a regra agressiva explica palavras visualmente fragmentadas.
- HTML/corpo não têm discrepância de quantidade de células.

### Causa mais provável

Combinação de densidade estrutural (11 colunas, checkbox isolado), `table-layout: fixed`, cabeçalhos deliberadamente quebráveis e colunas estreitas para títulos/conteúdo extensos. Há ainda forte risco de CSS antigo em cache ou de uma versão anterior às regras finais de 1800 px: as regras atuais, se efetivamente servidas, já impõem rolagem e não deveriam contrair a tabela abaixo de 1800 px. `app/web.py:1799-1828` e `3272-3277` confirmam que o servidor serve `app/panel.css` primeiro; falta verificar no navegador qual resposta foi realmente carregada.

Impacto: leitura lenta, cabeçalho alto/fragmentado e desalinhamento visual percebido, embora a contagem estrutural esteja correta.

Correção recomendada, sem executar: consolidar as três definições em uma única regra; revisar larguras com base no conteúdo; manter overflow horizontal; decidir quais cabeçalhos não quebram; incorporar o checkbox em “Situação”; considerar agrupar “produto + versão” para reduzir colunas; adicionar versionamento/cache-busting do asset. Depende de teste visual: DevTools deve confirmar CSS computado, largura real de 1800 px e arquivo/response atual.

## 9. Diagnóstico do pop-up de vinculação manual

### Caminho reconstruído

- Modal estático: `app/web.py:1621-1701`, inicialmente com classe `hidden`.
- Estilos visíveis/ocultos: `app/panel.css:2040-2161`; `.comparison-link-modal.hidden { display:none !important; }`.
- Candidato principal e botões: `app/panel.js:3944-4006`.
- “Ver outros”: `app/panel.js:3980-3986`.
- Evento real: `app/panel.js:4473-4492` abre `.comparison-details` e rola até `.comparison-candidates-summary`.
- Busca alternativa real: HTML inline criado somente dentro dos detalhes (`app/panel.js:3899-3942`), evento delegado em `4496-4590`.
- Pesquisa backend: `GET /comparacao/produtos` (`app/web.py:2954-3017`) retorna `{ok, role, query, products, total}` compatível com `searchComparisonLinkProducts()` (`app/panel.js:3435-3507`).
- Confirmação: `confirmManualComparisonRelationship()` (`3510-3585`) monta o par e chama `saveComparisonRelationship()` (`3258-3294`).
- Persistência: `POST /comparacao/vinculo/salvar` (`app/web.py:3306-3374`) chama `save_relationship()` (`app/comparison_decisions.py:511-686`).
- Atualização: após sucesso, o frontend notifica e executa recomparação forçada (`app/panel.js:3283-3291`).

### Causa comprovada

O modal é um componente órfão. Não existe referência JavaScript a `comparison_link_modal`, `comparison_link_modal_close`, `comparison_link_modal_query`, `comparison_link_modal_search`, `comparison_link_modal_suggestions` ou `comparison_link_modal_results`. Nenhum código remove a classe `hidden`. Logo, não é CSS acidental: o CSS corretamente o mantém oculto porque o evento/controlador nunca foi implementado. “Ver outros” foi conectado a um comportamento alternativo inline.

Impacto: o pop-up nunca aparece; a funcionalidade de busca fica escondida dentro do diagnóstico e diverge do UX planejado. Correção recomendada: escolher uma única interface, preferencialmente conectar o modal existente; adicionar estado/item ativo, renderização de candidatos, busca, seleção, confirmação/rejeição, fechamento acessível e tratamento de erro; remover ou harmonizar a implementação inline para não manter dois fluxos.

Dependência de teste: o código comprova a ausência do controlador. Um teste visual ainda é necessário depois da futura correção para foco, empilhamento, responsividade e atualização da linha.

## 10. Fluxo atual das decisões manuais

Há dois fluxos independentes:

1. **Decisão operacional da linha:** select/botões em `app/panel.js:4011-4026` e `4081`; POST individual/lote/restauração em `app/web.py:3376-3479`; `save_decision()` grava snapshot e histórico (`app/comparison_decisions.py:180-279`). As decisões são reaplicadas ao payload por `get_decisions_map()` no comparador. Banco atual: zero decisões e zero históricos.
2. **Relacionamento entre produtos:** confirmar/rejeitar candidato ou pesquisar outro (`app/panel.js:3297-3585`, `3820-4006`, `4416-4618`); POST em `/comparacao/vinculo/salvar`; persistência em `comparison_relationships`. Na recomparação, confirmado tem prioridade, rejeitado é filtrado, e “ausente” bloqueia matching automático (`app/comparison.py:1323-1594`).

Risco semântico: `same_product`/`different_products` coexistem com `manual_confirmed`/`manual_rejected`, mas apenas o segundo eixo muda efetivamente o pareamento. Impacto: usuário pode escolher “Mesmo produto” na decisão sem criar vínculo. Recomendação: explicitar na UI a diferença ou unificar a ação/transação.

## 11. Banco de dados e persistência

- Arquivo: `data/comparison_decisions.sqlite3`, configurado em `app/settings.py:43-45`.
- Tabelas: `comparison_decisions`, `comparison_decision_history`, `comparison_relationships`; índices correspondentes em `app/comparison_decisions.py:97-175`.
- Conexão: lock global, foreign keys, WAL e busy timeout; commit automático (`app/comparison_decisions.py:73-94`). Atenção: até funções de leitura chamam `initialize_database()`, e `database_connection()` executa `PRAGMA journal_mode=WAL`; por isso a aplicação não foi importada/executada nesta auditoria.
- Consulta `mode=ro`: integridade `ok`; 0 decisões; 0 históricos; 3 relacionamentos (1 confirmado, 1 rejeitado, 1 ausência confirmada). Os estados e textos gravados são coerentes com o código.
- Não há tabela de histórico de relacionamentos. Sobrescritas preservam somente `created_at`; rejeições automáticas de vínculos confirmados concorrentes também não deixam trilha de auditoria.
- A restrição `UNIQUE(site_product_key, source_product_key)` permite múltiplas linhas por produto, controladas por updates na aplicação. Não há constraint de banco garantindo um único `manual_confirmed` por lado.

Correções recomendadas: migrations versionadas; conexão de leitura que não inicialize/commite; histórico de relacionamentos; transação/constraint apropriada para exclusividade; testes de concorrência.

## 12. Erros, inconsistências e riscos encontrados

- **Confirmado — modal órfão:** seção 9.
- **Confirmado — CSS duplicado:** três definições de largura/layout da tabela (`app/panel.css:1235`, `2029`, `2164`).
- **Confirmado — mojibake:** diversos literais aparecem como `VÃ­nculo`, `SituaÃ§Ã£o`, `ðŸ...` em `app/web.py`, `app/panel.js`, `app/settings.py`, logs e documentação. Alguns textos do SQLite estão corretos, sugerindo histórico de codificações misturadas. Impacto: texto corrompido no painel/logs. Recomendação: auditar bytes/charset e corrigir em mudança dedicada, sem conversão em massa não revisada.
- **Confirmado — backup inválido:** `app/comparison_backup_indent.py:1846` tem `IndentationError`; módulos ativos passam. Impacto baixo enquanto não importado, mas polui verificações globais.
- **Confirmado — arquivos vazios/acidentais na raiz:** nomes como `node`, `python`, `dir`, `const`, `document.getElementById(id)` e outros. Impacto: ruído e risco de confundir scripts/ferramentas. Não removidos.
- **Confirmado — documentação defasada:** `leia-me.txt` descreve pastas não existentes.
- **Confirmado — ausência de Git detectável:** `git status` retorna “not a git repository”. A garantia final deve usar hash/inventário, não `git diff`.
- **Confirmado — cache não considera SQLite:** seção 3.
- **Confirmado — validação limitada do vínculo:** endpoint aceita chaves/metadados enviados pelo cliente e não comprova que os dois produtos existem nos catálogos selecionados (`app/web.py:3306-3341`). Impacto: registros órfãos/manipulados. Recomendação: validar server-side contra os catálogos e contexto.
- **Confirmado — origem/destino implícitos no banco:** relações não registram IDs/arquivos dos catálogos. Chaves iguais em comparações diferentes podem colidir semanticamente.
- **Confirmado — logs de coleta:** há ocorrências de HTTP 429, 404 e falhas DNS; não foram encontrados logs específicos do modal/decisões. São riscos da coleta, não causa dos dois defeitos de UI.
- **Não validado:** aparência real, cache HTTP do navegador e requests do painel. O sistema não foi iniciado para evitar escrita em slots/SQLite.

## 13. Próximos passos em ordem de prioridade

1. Em ambiente controlado/cópia do banco, abrir o painel e confirmar via DevTools o CSS servido/computado e o clique de “Ver outros”.
2. Implementar e testar o controlador do modal, reutilizando os endpoints e funções de persistência já existentes.
3. Consolidar o CSS da tabela e reduzir a densidade; incorporar o checkbox em “Situação” e avaliar agrupamento de colunas.
4. Adicionar testes do fluxo vínculo/rejeição/recomparação e do contrato das rotas.
5. Corrigir invalidação do cache por alterações de relacionamentos.
6. Fortalecer validação/contexto/histórico/migrations do SQLite.
7. Tratar mojibake, backups inválidos, arquivos acidentais e documentação em tarefas separadas.

## 14. Arquivos que provavelmente precisarão ser alterados

- `app/panel.js`: controlador/eventos/renderização do modal e possível remoção/harmonização do fluxo inline.
- `app/panel.css`: consolidar regras da tabela, larguras, quebra e responsividade; eventual refinamento do modal.
- `app/web.py`: somente se o HTML do modal/colunas ou validação do endpoint precisar mudar.
- `app/comparison.py`: invalidação do cache e, se necessário, ajuste do payload após vínculos.
- `app/comparison_decisions.py`: histórico, migrations, leitura sem escrita e garantias de integridade.
- `app/settings.py`: eventual versionamento de assets/configuração de banco.
- Novos arquivos de teste/documentação, ainda inexistentes.

Não há necessidade comprovada de alterar `app/storage.py`, `app/app.py`, `app/engine.py`, `app/models.py`, `app/adapters.py` ou `app/browser.py` para corrigir especificamente os dois problemas.

## 15. Comandos seguros para validação posterior

Executar a partir da raiz. Os comandos abaixo são somente leitura, exceto iniciar o app, que deve ser feito apenas sobre cópia isolada dos dados.

```powershell
# Sintaxe Python sem gerar .pyc
@'
import ast
from pathlib import Path
for p in list(Path('app').glob('*.py')) + [Path('main.py')]:
    ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
    print('OK', p)
'@ | python -

# Sintaxe JavaScript
node --check app/static/panel.js

# Referências do modal e tabela
rg -n "comparison_link_modal|comparison-view-candidates|comparison-table" app/web.py app/static/panel.js app/static/panel.css

# SQLite realmente somente leitura
@'
import sqlite3
from pathlib import Path
p = Path('data/comparison_decisions.sqlite3').resolve().as_posix()
con = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
print(con.execute('PRAGMA integrity_check').fetchone())
for t in ('comparison_decisions','comparison_decision_history','comparison_relationships'):
    print(t, con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
con.close()
'@ | python -

# Estado Git, caso a raiz seja futuramente versionada
git status --short
git diff -- PROJECT_STATUS.md
```

Para validação visual posterior: usar uma cópia de `data/` ou redirecionar o DB para uma cópia; iniciar o painel; em Network confirmar `/panel.css`, `/panel.js`, `/comparacao/produtos` e `/comparacao/vinculo/salvar`; em Elements confirmar largura computada de 1800 px, overflow do wrapper e remoção da classe `hidden` após a futura implementação.

## 16. Checklist cronológico atualizado

- [OK] Estrutura local completa inventariada; assets reais e HTML embutido localizados.
- [OK] Arquivos backend solicitados inspecionados e responsabilidades mapeadas.
- [OK] `app/static/panel.js`, `app/static/panel.css` e HTML da comparação inspecionados.
- [OK] Fluxo de matching seguro, candidatos, versões e estados reconstruído.
- [OK] Rotas de dados, pesquisa, decisões e vínculos rastreadas de ponta a ponta.
- [OK] SQLite consultado em modo somente leitura; schema, integridade e contagens confirmados.
- [OK] Logs relacionados pesquisados; sem log específico da UI, com erros de coleta 429/404/DNS registrados.
- [OK] Sintaxe de todos os módulos ativos e JavaScript validada.
- [PARCIAL] Decisões operacionais persistem, mas o banco atual ainda não contém registros desse eixo.
- [OK] Confirmação e rejeição de vínculos persistem e influenciam a comparação.
- [PARCIAL] Pesquisa/vínculo de qualquer produto existe inline, não no modal planejado.
- [PENDENTE] Conectar o modal e “Ver outros”; implementar fechamento, foco, busca e seleção.
- [PENDENTE] Oferecer rejeição coerente também no fluxo de pesquisa geral, se requerido.
- [PENDENTE] Consolidar/reprojetar cabeçalho e colunas; mover checkbox para “Situação”.
- [PENDENTE] Invalidar cache quando relacionamentos/decisões relevantes mudarem fora do fluxo forçado.
- [PENDENTE] Criar testes automatizados e migrations versionadas.
- [BLOQUEADO] Validação visual/runtime nesta auditoria: iniciar o app pode criar pastas, normalizar metadados e inicializar/alterar SQLite.
- [BLOQUEADO] `git diff`: a pasta não é um repositório Git; substituído por inventário e SHA-256 composto.
- [OK] Antes da documentação: 169 arquivos (excluindo `PROJECT_STATUS.md`), SHA-256 composto `e7a22b52ee90fbb86758e6480eb43042e8f6bc4b6642635418ff8aed71863b4e`.
- [OK] Única escrita autorizada nesta análise: este `PROJECT_STATUS.md`.

## 17. Plano de reorganização estrutural autorizado

Plano registrado antes das movimentações em 11/08/2026:

```text
/
├─ app/                         # módulos Python ativos
│  └─ static/                  # CSS e JavaScript ativos
├─ scripts/                    # utilitários operacionais identificados
├─ backups/
│  ├─ legacy_code/            # cópias antigas e código não executado
│  └─ unclassified/           # artefatos acidentais preservados
├─ docs/legacy/                # documentação histórica
├─ data/                       # dados operacionais, sem movimentação e fora do Git
├─ logs/                       # logs operacionais, sem movimentação e fora do Git
├─ main.py                     # entrada preservada
├─ README.md                   # documentação principal atual
├─ PROJECT_STRUCTURE.md        # mapa estrutural real
└─ PROJECT_STATUS.md           # diagnóstico e acompanhamento
```

Princípios: preservar os nomes dos módulos ativos; mover somente assets com atualização explícita de caminhos; não criar diretórios vazios; não mover dados, banco ou logs; manter todos os backups; separar utilitários atuais de scripts históricos; manter `python main.py` e `autoscraper.bat` como entradas.

## 18. Resultado da reorganização estrutural

### Proteção e segurança

- Git 2.51.1 disponível; repositório local inicializado, sem remoto criado.
- Commit baseline criado antes das movimentações: `409b564ae89ed695f0d91e18be558e86dc7b353a`.
- `.gitignore` exclui bytecode, caches, ambientes, `.env`, logs, SQLite/WAL/SHM, catálogos importados, temporários e dados operacionais; somente o mascote necessário é incluído dentro de `data/`.
- A auditoria encontrou e removeu do código ativo defaults reais de e-mail/senha em `app/settings.py:324-370`. O suporte já existente a variáveis de ambiente foi preservado. O backup histórico com os valores antigos está localmente preservado em `backups/legacy_code/app/settings.py.backup-antes-decisions-db` e explicitamente ignorado pelo Git.

### Movimentações realizadas

- `app/panel.js` → `app/static/panel.js`; `app/panel.css` → `app/static/panel.css`.
- Todos os `app/*.backup-*`, `app/comparison_backup_indent.py` e `app/antigo/` → `backups/legacy_code/app/`.
- Backups de código de `backups 04-08/` → `backups/legacy_code/2026-08-04/`; os dois CSVs históricos permaneceram no lugar e ignorados.
- `corrigir_web.py/.bat` → `backups/legacy_code/scripts/`, pois são um reparo pontual antigo que altera `web.py`.
- `converter_imports.py` e `inspecionar_planilhas.py` → `scripts/`.
- `leia-me.txt`, `comparison_numerado.txt`, `etapa1_web_abas.txt` e `etapa2_js_abas.txt` → `docs/legacy/`.
- 19 artefatos acidentais da raiz → `backups/unclassified/`, com origem e conteúdo registrados no README local.

### Código e documentação alterados

- `app/settings.py`: paths de assets atualizados para `app/static/` e credenciais hardcoded removidas.
- `.gitignore`: regras específicas do projeto.
- `README.md`: documentação operacional atual, configuração segura e comando de início.
- `PROJECT_STRUCTURE.md`: árvore real e responsabilidades.
- `PROJECT_STATUS.md`: plano, resultado e checklist atualizados.

Nenhum módulo Python ativo foi renomeado ou internamente refatorado. O cabeçalho da tabela e o modal não foram corrigidos nesta etapa.

### Validações realizadas

- [OK] AST de 10 módulos ativos em `app/`, `main.py` e 2 utilitários em `scripts/`.
- [OK] `node --check app/static/panel.js`.
- [OK] Importação com `python -B` de settings, models, adapters, browser, storage, engine, app, comparison_decisions, comparison, web e main.
- [OK] Paths importados confirmados: CSS/JS em `app/static/`, DB em `data/comparison_decisions.sqlite3` e importações em `data/imports`.
- [OK] Hash do SQLite e quantidade de arquivos em `data/`/`logs/` permaneceram inalterados durante o teste de imports.
- [OK] Nenhum import/referência ativa a `backup`, `antigo`, `legacy_code` ou `comparison_backup_indent`.
- [OK] Nenhuma referência ativa aos paths antigos `app/panel.js` e `app/panel.css`.
- [OK] Defaults de credenciais ativos confirmados vazios; resolução por ambiente preservada.
- [BLOQUEADO] Teste visual/HTTP completo não executado: a inicialização normal prepara slots e pode escrever dados. Não foi necessário iniciar o sistema para validar a reorganização de paths/imports.

### Checklist após reorganização

- [OK] Código ativo separado de frontend, scripts, documentação histórica, backups e artefatos não classificados.
- [OK] Dados operacionais, SQLite, catálogos e logs mantidos em seus paths originais.
- [OK] Backup inválido retirado das verificações do código ativo e preservado.
- [OK] README principal agora descreve a implementação real.
- [OK] Nenhuma pasta de testes vazia criada; ainda não há testes automatizados reais.
- [PENDENTE] Criar manifesto reproduzível de dependências após confirmar versões usadas no ambiente.
- [PENDENTE] Corrigir o cabeçalho da comparação em tarefa própria.
- [PENDENTE] Implementar/conectar o modal de vínculo em tarefa própria.

## 19. Modal de vinculação e tabela de comparação

Implementado na branch `feat/modal-vinculacao-ui` em 11/08/2026:

- o modal existente passou a controlar a linha ativa, candidatos, pesquisa no catálogo oposto, confirmação e rejeição;
- abertura por **Ver outros**, fechamento por botão, Escape e backdrop, contenção de foco e retorno ao acionador;
- pesquisa por Enter, botão e debounce, com carregamento, vazio, erro e retorno por `aria-live`;
- confirmação/rejeição reutilizam `/comparacao/vinculo/salvar` e forçam `/comparacao/data?force=1`;
- a rota de vínculo agora valida as chaves nos dois catálogos selecionados;
- o fluxo de pesquisa inline redundante foi removido;
- checkbox incorporado a **Situação**, reduzindo a tabela de 11 para 10 colunas;
- regras duplicadas de `.comparison-table` consolidadas, sem `overflow-wrap:anywhere`, com cabeçalho fixo e rolagem nos dois eixos;
- `panel.css` e `panel.js` recebem `?v=<mtime_ns>` para invalidação simples do cache;
- testes automatizados usam somente SQLite temporário.

Validação visual real permaneceu pendente porque o navegador interno não pôde ser conectado nesta sessão; não foi inferida qualidade visual apenas pela sintaxe.
