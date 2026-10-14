@echo off
:: adDominum -- startup wrapper (14 Oct 2026 boot-reliability fix)
:: Fired by Task Scheduler: daily 07:58 AND at logon (after restart / cold boot / fast startup).
:: Backup of previous version: C:\Users\ellyo\data\addominum-fix\backup-20261014\start_addominum.bat
setlocal
set TRIG=%~1
if "%TRIG%"=="" set TRIG=scheduled
set PROJ=C:\Projects\adDominum
set PY=C:\Users\ellyo\AppData\Local\Programs\Python\Python313\python.exe
set PYTHONPATH=%PROJ%
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d %PROJ%
if not exist logs mkdir logs
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set TODAY=%%d

:: --- Papal catch-up (logon only; independent of the daily checks below) ---
if /i "%TRIG%"=="logon" call :papal
:: Skip if today's plan already finished (prevents a second plan on a later logon the same day)
if exist logs\done-%TODAY%.flag (
  echo [%date% %time%] SKIP [%TRIG%]: today's plan already completed >> logs\startup.log
  exit /b 0
)

:: Skip if main.py is already running (e.g. the 07:58 run is still in progress)
powershell -NoProfile -ExecutionPolicy Bypass -File utils\addominum_running.ps1
if errorlevel 1 (
  echo [%date% %time%] SKIP [%TRIG%]: main.py already running >> logs\startup.log
  exit /b 0
)

echo [%date% %time%] WRAPPER START [%TRIG%], waiting for network >> logs\startup.log
:: Wait up to ~5 minutes for network / DNS to api.x.com
set /a N=0
:netwait
curl.exe -s -o nul --max-time 10 https://api.x.com && goto netok
set /a N+=1
if %N% GEQ 20 (
  echo [%date% %time%] WARN: network not ready after %N% tries, starting anyway >> logs\startup.log
  goto run
)
timeout /t 15 /nobreak >nul
goto netwait
:netok
echo [%date% %time%] network OK after %N% retries >> logs\startup.log
:run
echo Starting adDominum at %date% %time% >> logs\startup.log
"%PY%" main.py >> logs\automation.log 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%] main.py exited rc=%RC% >> logs\startup.log
if "%RC%"=="0" echo done> logs\done-%TODAY%.flag
exit /b %RC%

:papal
for /f "delims=" %%r in ('powershell -NoProfile -ExecutionPolicy Bypass -File utils\papal_due.ps1 -Proj "%PROJ%"') do set PREASON=%%r
powershell -NoProfile -ExecutionPolicy Bypass -File utils\papal_due.ps1 -Proj "%PROJ%" >nul
if errorlevel 1 (
  echo [%date% %time%] PAPAL SKIP [%TRIG%]: %PREASON% >> logs\startup.log
  goto :eof
)
echo [%date% %time%] PAPAL CATCH-UP START [%TRIG%]: %PREASON% >> logs\startup.log
"%PY%" publishing\papal_feed.py --live >> logs\papal_automation.log 2>&1
echo [%date% %time%] PAPAL CATCH-UP exited rc=%ERRORLEVEL% >> logs\startup.log
goto :eof