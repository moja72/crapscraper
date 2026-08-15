# Estrutura do projeto CrapScraper

Mapa atualizado em 11/08/2026. A estrutura foi mantida simples: os módulos ativos continuam com os mesmos nomes e apenas assets, utilitários, legado e documentação histórica foram separados.

```text
crapscraper4/
├─ app/
│  ├─ adapters.py
│  ├─ app.py
│  ├─ browser.py
│  ├─ comparison.py
│  ├─ comparison_decisions.py
│  ├─ engine.py
│  ├─ models.py
│  ├─ settings.py
│  ├─ storage.py
│  ├─ web.py
│  └─ static/
│     ├─ panel.css
│     └─ panel.js
├─ scripts/
│  ├─ converter_imports.py
│  └─ inspecionar_planilhas.py
├─ tests/
│  └─ test_comparison_modal.py
├─ backups/
│  ├─ legacy_code/
│  └─ unclassified/
├─ docs/
│  └─ legacy/
├─ data/
├─ logs/
├─ .gitignore
├─ autoscraper.bat
├─ main.py
├─ README.md
├─ PROJECT_STATUS.md
└─ PROJECT_STRUCTURE.md
```

## Código ativo

- `main.py`: entrada oficial; prepara o slot/contexto, instancia `ScraperApp` e chama o servidor.
- `app/settings.py`: paths, sites, tipos, contas e opções. Credenciais são resolvidas por variáveis de ambiente. Os assets ativos apontam para `app/static/`.
- `app/models.py`: modelos de contexto, execução, categorias, catálogo e estado.
- `app/adapters.py`: regras específicas de listagem/detalhes para os sites suportados.
- `app/browser.py`: sessão Playwright, autenticação e navegação controlada.
- `app/engine.py`: coleta HTTP/DOM, paginação, detalhes, filas e fluxo do scraper.
- `app/storage.py`: slots, catálogos, estado, caches, configurações e logs.
- `app/app.py`: estado de execução, controles, aplicação e gerenciador de runs.
- `app/comparison.py`: normalização, matching, candidatos, comparação de versões e paginação.
- `app/comparison_decisions.py`: SQLite de decisões e vínculos manuais.
- `app/web.py`: servidor HTTP, rotas e HTML do painel.
- `app/static/panel.js` e `panel.css`: frontend ativo servido por `app/web.py`.

## Dados operacionais

`data/` mantém slots, catálogos, importações e o SQLite. `logs/` mantém logs de runtime. Esses diretórios permanecem em seus caminhos originais para preservar o funcionamento e são ignorados pelo Git, com exceção do asset `data/crapscrapper mascote.webp` necessário ao painel.

O diretório legado `backups 04-08/` permanece apenas com dois CSVs históricos. Eles não foram movidos porque são catálogos/dados operacionais e não havia necessidade funcional comprovada; a extensão global `*.csv` os mantém fora do Git.

## Scripts auxiliares

`scripts/` contém somente utilitários identificados e ainda úteis. Eles não são importados pelo app. Devem ser executados a partir da raiz para conservar seus paths relativos.

## Testes

`tests/test_comparison_modal.py` valida os contratos estruturais do modal e da tabela, a existência de produtos nos catálogos e confirmação/rejeição em um SQLite temporário. A suíte não escreve no banco operacional.

## Backups e legado

- `backups/legacy_code/app/`: todos os arquivos `*.backup-*`, `comparison_backup_indent.py` e o antigo `app/antigo/`.
- `backups/legacy_code/2026-08-04/`: backups de código que estavam na pasta `backups 04-08/`.
- `backups/legacy_code/scripts/`: script pontual antigo de correção do `web.py` e seu `.bat`.
- `backups/unclassified/`: arquivos acidentais da raiz, preservados sem participar da execução.

Backups não devem ser importados, compilados como código ativo nem usados como fonte atual. `comparison_backup_indent.py` continua preservado apesar do erro histórico de indentação.

## Documentação

- `README.md`: orientação principal atual.
- `PROJECT_STRUCTURE.md`: este mapa.
- `PROJECT_STATUS.md`: diagnóstico e histórico do trabalho.
- `docs/legacy/`: árvore arquitetural antiga e fragmentos usados durante etapas anteriores. Seu conteúdo é histórico e pode conter mojibake original.

## Arquivos temporários e gerados

Bytecode, caches, ambientes virtuais, arquivos `.env`, bancos, logs, catálogos e arquivos temporários são excluídos pelo `.gitignore`. Não existem diretórios vazios criados para uma arquitetura futura.
