@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "CRAPSCRAPER_PID=%~dp0.runtime\server.pid"
if not exist "%CRAPSCRAPER_PID%" (
  echo [CrapScraper] Nenhuma instancia iniciada pelo launcher foi encontrada.
  exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pidFile='%CRAPSCRAPER_PID%';" ^
  "$serverPid=[int](Get-Content -LiteralPath $pidFile -ErrorAction Stop | Select-Object -First 1);" ^
  "$process=Get-Process -Id $serverPid -ErrorAction SilentlyContinue;" ^
  "if(-not $process){Remove-Item -LiteralPath $pidFile -Force; Write-Host '[CrapScraper] Registro obsoleto removido; nenhuma instancia estava ativa.'; exit 0};" ^
  "if($process -and $process.ProcessName -in @('python','pythonw')){Stop-Process -Id $serverPid -Force; Remove-Item -LiteralPath $pidFile -Force; exit 0};" ^
  "Write-Host '[CrapScraper] O PID salvo nao pertence ao servidor esperado; nada foi encerrado.'; exit 2"
exit /b %errorlevel%
