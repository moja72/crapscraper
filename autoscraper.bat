@echo off
title CrapScraper
cd /d "%~dp0"

echo Iniciando CrapScraper...
echo.

rem A escrita continua protegida por preview, plano, fila e confirmação individual.
set "SCRAPER_UPDATE_EXECUTION_ENABLED=1"
set "SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS=*"

python main.py

echo.
echo Processo finalizado.
pause
