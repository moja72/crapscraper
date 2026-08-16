@echo off
title CrapScraper
cd /d "%~dp0"

echo Iniciando CrapScraper...
echo.

rem Evita uma segunda instancia disputando a porta 8765. Se o painel ja estiver
rem ativo, apenas abre a instancia existente no navegador.
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2).read()" >nul 2>&1
if not errorlevel 1 (
    echo CrapScraper ja esta em execucao. Abrindo o painel existente...
    start "" "http://127.0.0.1:8765/"
    exit /b 0
)

rem A escrita continua protegida por preview, plano, fila e confirmação individual.
set "SCRAPER_UPDATE_EXECUTION_ENABLED=1"
set "SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS=*"
set "SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED=1"

python main.py

echo.
echo Processo finalizado.
pause
