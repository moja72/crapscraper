@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "CRAPSCRAPER_PORT=%SCRAPER_PORT%"
if not defined CRAPSCRAPER_PORT set "CRAPSCRAPER_PORT=8766"
set "CRAPSCRAPER_PID=%~dp0.runtime\server.pid"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=[int]'%CRAPSCRAPER_PORT%'; $pidFile='%CRAPSCRAPER_PID%'; $serverPid=$null;" ^
  "if(Test-Path -LiteralPath $pidFile){try{$serverPid=[int](Get-Content -LiteralPath $pidFile -ErrorAction Stop | Select-Object -First 1)}catch{$serverPid=$null}};" ^
  "if(-not $serverPid){$listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($listener){$serverPid=[int]$listener.OwningProcess}};" ^
  "if(-not $serverPid){Write-Host '[CrapScraper] Nenhuma instancia ativa encontrada.'; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 0};" ^
  "$process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $serverPid) -ErrorAction SilentlyContinue;" ^
  "if(-not $process){Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; Write-Host '[CrapScraper] Registro obsoleto removido; nenhuma instancia estava ativa.'; exit 0};" ^
  "$name=[IO.Path]::GetFileNameWithoutExtension([string]$process.Name); $command=[string]$process.CommandLine;" ^
  "if($name -notin @('python','pythonw') -or $command -notmatch 'main\.py'){Write-Host ('[CrapScraper] A porta ' + $port + ' pertence a outro processo; nada foi encerrado. PID ' + $serverPid); exit 2};" ^
  "Stop-Process -Id $serverPid -Force -ErrorAction Stop; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; Write-Host ('[CrapScraper] Instancia encerrada. PID ' + $serverPid); exit 0"
exit /b %errorlevel%
