@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "CRAPSCRAPER_PORT=%SCRAPER_PORT%"
if not defined CRAPSCRAPER_PORT set "CRAPSCRAPER_PORT=8766"
set "CRAPSCRAPER_URL=http://127.0.0.1:%CRAPSCRAPER_PORT%"
set "CRAPSCRAPER_RUNTIME=%~dp0.runtime"
set "CRAPSCRAPER_PID=%CRAPSCRAPER_RUNTIME%\server.pid"

call :health
if not errorlevel 1 goto open_browser

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
python.exe -c "import os,subprocess,sys; os.makedirs('.runtime',exist_ok=True); out=open(r'.runtime\server.stdout.log','ab'); err=open(r'.runtime\server.stderr.log','ab'); process=subprocess.Popen([sys.executable,'main.py'],cwd=os.getcwd(),stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS); print(process.pid)" > "%CRAPSCRAPER_PID%"
if errorlevel 1 (
  echo [CrapScraper] Nao foi possivel iniciar o servidor.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='%CRAPSCRAPER_URL%/api/health'; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-RestMethod -Uri $url -TimeoutSec 1; if($r.ok){exit 0} } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
  echo.
  echo [CrapScraper] O servidor nao respondeu a tempo.
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
