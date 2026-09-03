@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "CRAPSCRAPER_ROOT=%%~fI"
cd /d "%CRAPSCRAPER_ROOT%"

set "CRAPSCRAPER_PORT=%SCRAPER_PORT%"
if not defined CRAPSCRAPER_PORT set "CRAPSCRAPER_PORT=8766"
set "CRAPSCRAPER_URL=http://127.0.0.1:%CRAPSCRAPER_PORT%"
set "CRAPSCRAPER_RUNTIME=%CRAPSCRAPER_ROOT%\.runtime"
set "CRAPSCRAPER_PID=%CRAPSCRAPER_RUNTIME%\server.pid"

rem O launcher local habilita as escritas da Loja e a execucao real de adicoes por padrao.
rem Defina SCRAPER_STORE_WRITE_ENABLED=0 para iniciar a Loja em somente leitura.
rem Defina SCRAPER_ADDITION_EXECUTION_ENABLED=0 para bloquear explicitamente a criacao de novos produtos.
if not defined SCRAPER_STORE_WRITE_ENABLED set "SCRAPER_STORE_WRITE_ENABLED=1"
if not defined SCRAPER_ADDITION_EXECUTION_ENABLED set "SCRAPER_ADDITION_EXECUTION_ENABLED=1"

call :health
if errorlevel 1 goto start_server
call :health_write
if not errorlevel 1 goto open_browser

echo [CrapScraper] Instancia antiga, em somente leitura ou com adicoes reais desabilitadas. Reiniciando...
call :stop_existing
if errorlevel 1 (
  echo.
  echo [CrapScraper] Nao foi possivel reiniciar a instancia existente com seguranca.
  echo Feche manualmente o processo que esta usando a porta %CRAPSCRAPER_PORT% e tente novamente.
  echo.
  pause
  exit /b 1
)
timeout /t 1 /nobreak >nul

:start_server
where python.exe >nul 2>nul
if errorlevel 1 (
  echo.
  echo [CrapScraper] Python nao foi encontrado no PATH.
  echo Instale o Python ou adicione python.exe ao PATH do Windows.
  echo.
  pause
  exit /b 1
)

if not exist "%CRAPSCRAPER_RUNTIME%" mkdir "%CRAPSCRAPER_RUNTIME%" >nul 2>nul
echo [CrapScraper] Iniciando servidor em %CRAPSCRAPER_URL% ...
python.exe -c "import os,subprocess,sys; root=r'%CRAPSCRAPER_ROOT%'; runtime=r'%CRAPSCRAPER_RUNTIME%'; os.makedirs(runtime,exist_ok=True); out=open(os.path.join(runtime,'server.stdout.log'),'ab'); err=open(os.path.join(runtime,'server.stderr.log'),'ab'); process=subprocess.Popen([sys.executable,os.path.join(root,'main.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS); print(process.pid)" > "%CRAPSCRAPER_PID%"
if errorlevel 1 (
  echo [CrapScraper] Nao foi possivel iniciar o servidor.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='%CRAPSCRAPER_URL%/api/health'; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-RestMethod -Uri $url -TimeoutSec 1; if($r.ok -and $r.store_write_enabled -eq $true){exit 0} } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$pidFile='%CRAPSCRAPER_PID%'; if(Test-Path -LiteralPath $pidFile){ $serverPid=[int](Get-Content -LiteralPath $pidFile | Select-Object -First 1); $process=Get-Process -Id $serverPid -ErrorAction SilentlyContinue; if($process -and $process.ProcessName -in @('python','pythonw')){Stop-Process -Id $serverPid -Force}; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue }"
  echo.
  echo [CrapScraper] O servidor nao iniciou com a escrita da Loja habilitada.
  echo Consulte: "%CRAPSCRAPER_RUNTIME%\server.stderr.log"
  echo.
  pause
  exit /b 1
)

:open_browser
echo [CrapScraper] Interface disponivel em %CRAPSCRAPER_URL%
if /I "%CRAPSCRAPER_NO_BROWSER%"=="1" goto done
start "" "%CRAPSCRAPER_URL%"

:done
exit /b 0

:health
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r=Invoke-RestMethod -Uri '%CRAPSCRAPER_URL%/api/health' -TimeoutSec 1; if($r.ok){exit 0} } catch {}; exit 1" >nul 2>nul
exit /b %errorlevel%

:health_write
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r=Invoke-RestMethod -Uri '%CRAPSCRAPER_URL%/api/health' -TimeoutSec 1; if($r.ok -and $r.app -eq 'CrapScraper' -and $r.store_write_enabled -eq $true){exit 0} } catch {}; exit 1" >nul 2>nul
exit /b %errorlevel%

:stop_existing
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=[int]'%CRAPSCRAPER_PORT%'; $pidFile='%CRAPSCRAPER_PID%'; $serverPid=$null;" ^
  "if(Test-Path -LiteralPath $pidFile){try{$serverPid=[int](Get-Content -LiteralPath $pidFile -ErrorAction Stop | Select-Object -First 1)}catch{$serverPid=$null}};" ^
  "if(-not $serverPid){$listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($listener){$serverPid=[int]$listener.OwningProcess}};" ^
  "if(-not $serverPid){exit 0};" ^
  "$process=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $serverPid) -ErrorAction SilentlyContinue;" ^
  "if(-not $process){Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 0};" ^
  "$name=[IO.Path]::GetFileNameWithoutExtension([string]$process.Name); $command=[string]$process.CommandLine;" ^
  "if($name -notin @('python','pythonw') -or $command -notmatch 'main\.py'){Write-Host ('[CrapScraper] A porta ' + $port + ' pertence a outro processo: PID ' + $serverPid); exit 2};" ^
  "Stop-Process -Id $serverPid -Force -ErrorAction Stop; Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue; exit 0"
exit /b %errorlevel%
