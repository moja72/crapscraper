# CrapScraper

CrapScraper é uma aplicação local em Python para coletar catálogos, acompanhar execuções por slots e comparar produtos do UltrapackV2 com catálogos importados do PluginTema.

## Requisitos

- Python compatível com as dependências já usadas pelo projeto.
- Git para controle local de versão.
- Node.js é opcional e usado apenas para validar a sintaxe do JavaScript.
- Credenciais fornecidas por variáveis de ambiente; não há credenciais válidas no código versionado.

As principais dependências importadas pelo código são Playwright, Requests, Beautiful Soup e OpenPyXL. Esta reorganização não instalou nem atualizou dependências e o projeto ainda não possui manifesto de dependências versionado.

## Configuração de credenciais

Defina somente as variáveis correspondentes à conta utilizada:

```powershell
$env:SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL='...'
$env:SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD='...'
$env:SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_EMAIL='...'
$env:SCRAPER_PLUGINTHEME_COPRODUCAOLANCAMENTOS_PASSWORD='...'

$env:SCRAPER_ULTRAPACKV2_BERNARDES1992_EMAIL='...'
$env:SCRAPER_ULTRAPACKV2_BERNARDES1992_PASSWORD='...'
$env:SCRAPER_PLUGINTHEME_BERNARDES1992_EMAIL='...'
$env:SCRAPER_PLUGINTHEME_BERNARDES1992_PASSWORD='...'
```

Não grave valores reais em arquivos versionados. Arquivos `.env`, bancos, logs, catálogos e dados operacionais estão excluídos pelo `.gitignore`.

## Inicialização

Na raiz do projeto:

```powershell
python main.py
```

No Windows também é possível executar `autoscraper.bat`. O comando prepara os diretórios/slots necessários e inicia o painel HTTP local; portanto ele modifica dados operacionais em `data/` durante o uso normal.

## Estrutura e documentação

- `app/`: backend e frontend ativos.
- `app/static/`: JavaScript e CSS servidos pelo painel.
- `scripts/`: utilitários operacionais independentes.
- `data/` e `logs/`: estado local não versionado.
- `backups/`: código histórico e artefatos preservados, fora do caminho de importação ativo.
- `docs/legacy/`: documentação histórica que não descreve o estado atual.
- `PROJECT_STRUCTURE.md`: árvore e responsabilidades atuais.
- `PROJECT_STATUS.md`: diagnóstico, riscos e checklist da evolução.

## Comparação de catálogos

O painel lista catálogos salvos/importados, normaliza as duas fontes, cria correspondências seguras, sugere candidatos aproximados, compara versões e persiste decisões manuais em `data/comparison_decisions.sqlite3`. A tabela de comparação possui sete colunas. **Produtos** e **Versões** mostram PluginTema → Ultrapack, nessa ordem, usando `—` para dados ausentes; **Recomendação** abre um modal de diagnóstico com os dados completos da linha. A seleção em lote permanece na coluna Situação. Quando existe candidato acionável, a coluna Candidato principal exibe os ícones acessíveis de confirmação e rejeição seguidos de **Ver outros**, que abre o modal de vínculo para pesquisar o catálogo oposto. As gravações validam as chaves nos catálogos selecionados e forçam a recomparação.

Testes focados podem ser executados sem usar o banco operacional:

```powershell
python -m unittest discover -s tests -v
```

## Utilitários

Execute os scripts a partir da raiz, pois eles usam caminhos relativos ao projeto:

```powershell
python scripts/converter_imports.py
python scripts/inspecionar_planilhas.py
```

O primeiro converte planilhas de `data/imports`; o segundo inspeciona planilhas de `data/comparacao/entrada`. Ambos podem ler ou gerar dados operacionais e não fazem parte da inicialização normal.

## Segurança e versionamento

O repositório é somente local e não possui remoto configurado. Antes de qualquer publicação futura, revise o histórico, o `.gitignore` e os arquivos em `backups/`, especialmente backups antigos que podem conter informações particulares.
