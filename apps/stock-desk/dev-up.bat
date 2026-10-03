@echo off
setlocal enabledelayedexpansion
title stock-desk dev-up

REM One-click launcher for stock-desk on Windows: git pull + backend + scheduler + frontend.
REM Double-click it or run it from any directory; all paths derive from %~dp0.
REM Backend and scheduler MUST start from the backend directory so SQLite resolves to the same ./data/stock-desk.db.
REM Order: backend, then wait for /health, then scheduler, then frontend, then status lines.

set "TARGET_BRANCH=product/stock-desk"
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"

REM ---- 1. prerequisites ----
set "MISSING="
where git >nul 2>nul
if errorlevel 1 (
  echo [MISSING] git - install from https://git-scm.com/download/win
  set "MISSING=1"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
  set "MISSING=1"
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [MISSING] npm - install Node.js from https://nodejs.org
  set "MISSING=1"
)
if defined MISSING (
  echo After installing, run this script again.
  goto fail
)

set "HAVE_CURL="
where curl.exe >nul 2>nul
if not errorlevel 1 set "HAVE_CURL=1"

REM ---- 2. repo state checks ----
git -C "%REPO_ROOT%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Not a git repo: !REPO_ROOT!
  goto fail
)

REM Tracked changes only: untracked files do not block a fast-forward pull.
set "DIRTY="
for /f "delims=" %%L in ('git -C "%REPO_ROOT%" status --porcelain --untracked-files=no') do set "DIRTY=1"
if defined DIRTY (
  echo [STOP] You have local changes to tracked files. Please tell Claude before continuing.
  goto fail
)

set "CUR_BRANCH="
for /f "delims=" %%B in ('git -C "%REPO_ROOT%" rev-parse --abbrev-ref HEAD') do set "CUR_BRANCH=%%B"
if not "!CUR_BRANCH!"=="%TARGET_BRANCH%" (
  echo Current branch is !CUR_BRANCH!, not %TARGET_BRANCH%
  choice /c YN /n /m "Switch to %TARGET_BRANCH%? [Y/N] "
  if errorlevel 2 (
    echo Cancelled.
    goto fail
  )
  git -C "%REPO_ROOT%" checkout %TARGET_BRANCH%
  if errorlevel 1 (
    echo [ERROR] Branch switch failed
    goto fail
  )
)

REM ---- 3. pull latest code ----
echo.
echo [1/4] Updating code (git pull)
git -C "%REPO_ROOT%" pull --ff-only origin %TARGET_BRANCH%
if errorlevel 1 (
  echo [ERROR] git pull failed - please send a screenshot of the messages above to Claude
  goto fail
)

REM ---- 4. stop old processes (before install, so Windows does not lock .venv / node_modules) ----
echo.
echo [2/4] Checking for old processes on port 8000 / 3000 and for an old scheduler
call :ensure_port_free 8000
if errorlevel 1 goto fail
call :ensure_port_free 3000
if errorlevel 1 goto fail
call :ensure_scheduler_free
if errorlevel 1 goto fail

REM ---- 5. dependencies ----
echo.
echo [3/4] Installing dependencies
pushd "%BACKEND_DIR%"
uv sync --locked
if errorlevel 1 (
  popd
  echo [ERROR] Backend uv sync failed
  goto fail
)
popd
pushd "%FRONTEND_DIR%"
REM npm is a .cmd file: it needs CALL, otherwise this script would stop after it.
call npm install --no-save
if errorlevel 1 (
  popd
  echo [ERROR] Frontend npm install failed
  goto fail
)
popd

REM ---- 6. backend first, then (after /health) scheduler + frontend; each in its own window kept open by /k ----
echo.
echo [4/4] Starting backend, scheduler and frontend
start "stock-desk backend" cmd /k "cd /d "%BACKEND_DIR%" && uv run uvicorn app.main:app --reload --port 8000"

REM ---- 7. wait for backend /health (max 60s) ----
echo Waiting for backend /health (up to 60 seconds)...
set /a TRIES=0
:wait_backend
call :probe "http://localhost:8000/health"
if not errorlevel 1 goto backend_ok
set /a TRIES+=1
if !TRIES! GEQ 30 goto backend_timeout
call :sleep2
goto wait_backend

:backend_ok
echo Backend is healthy. Starting scheduler and frontend.
REM Same directory as the backend, so both use the same SQLite file. Env vars (STOCK_DESK_DB_PATH, FINMIND_API_TOKEN) are inherited.
start "stock-desk scheduler" cmd /k "cd /d "%BACKEND_DIR%" && uv run python -m app.scheduler"
start "stock-desk frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

REM ---- 8. wait for frontend (max 90s) ----
echo Waiting for frontend (up to 90 seconds)...
set /a TRIES=0
:wait_frontend
call :probe "http://localhost:3000"
if not errorlevel 1 goto frontend_ok
set /a TRIES+=1
if !TRIES! GEQ 45 goto frontend_timeout
call :sleep2
goto wait_frontend

:frontend_ok
REM ---- 9. status lines for the three processes ----
call :sleep2
echo.
call :probe "http://localhost:8000/health"
if errorlevel 1 (echo [FAIL] backend   not answering at http://localhost:8000/health) else (echo [OK]   backend   http://localhost:8000/health)
call :check_scheduler
if errorlevel 1 (echo [FAIL] scheduler not running - check the 'stock-desk scheduler' window. The app still works but there is no background refresh or alerts.) else (echo [OK]   scheduler running - window 'stock-desk scheduler')
call :probe "http://localhost:3000"
if errorlevel 1 (echo [FAIL] frontend  not answering at http://localhost:3000) else (echo [OK]   frontend  http://localhost:3000)
REM Empty first quoted arg is the window title; otherwise start treats the URL as the title.
start "" "http://localhost:3000"
echo.
echo Done.
echo To stop: close the three stock-desk windows.
echo URL: http://localhost:3000
echo.
pause
exit /b 0

:backend_timeout
echo.
echo [TIMEOUT] Backend did not become healthy in time. Check the error in the 'stock-desk backend' window and send a screenshot to Claude.
goto fail

:frontend_timeout
echo.
echo [TIMEOUT] Frontend did not start in time. Check the error in the 'stock-desk frontend' window and send a screenshot to Claude.
goto fail

:fail
echo.
pause
exit /b 1

REM ---- subroutines ----

:sleep2
REM About 2 seconds; ping works even when stdin is redirected (timeout does not).
ping -n 3 127.0.0.1 >nul
exit /b 0

:probe
REM %~1 = URL. Returns errorlevel 0 when the server answers with a non-error status.
if not defined HAVE_CURL goto probe_ps
curl.exe -s -f --max-time 3 -o NUL "%~1"
exit /b %errorlevel%
:probe_ps
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri '%~1' | Out-Null; exit 0 } catch { exit 1 }"
exit /b %errorlevel%

:scan_port
REM %~1 = 4-digit port. Sets PORT_PIDS to a space-padded unique PID list (" " = none).
REM Only LISTENING rows whose local address ends exactly with :PORT (IPv4 and [::] alike).
REM Last 5 chars of the address are compared, so :80001 and :18000 never match :8000.
set "PORT_PIDS= "
for /f "tokens=2,4,5" %%a in ('netstat -ano ^| findstr /C:"LISTENING"') do (
  set "ADDR=%%a"
  if /i "%%b"=="LISTENING" if "!ADDR:~-5!"==":%~1" (
    if "!PORT_PIDS: %%c =!"=="!PORT_PIDS!" set "PORT_PIDS=!PORT_PIDS!%%c "
  )
)
exit /b 0

:ensure_port_free
REM %~1 = port. Asks before killing; returns errorlevel 1 if the port stays occupied.
call :scan_port %~1
if "!PORT_PIDS!"==" " exit /b 0
echo.
echo [NOTICE] Port %~1 is already in use:
for %%P in (!PORT_PIDS!) do (
  if "%%P"=="4" (
    echo   PID 4 is a Windows system process and cannot be stopped. Reboot and try again.
    exit /b 1
  )
  for /f "tokens=1" %%N in ('tasklist /FI "PID eq %%P" /NH') do echo   PID %%P: %%N
)
choice /c YN /n /m "Stop the old process? [Y/N] "
if errorlevel 2 (
  echo Cancelled. Not starting a second copy.
  exit /b 1
)
for %%P in (!PORT_PIDS!) do taskkill /PID %%P /F /T
call :sleep2
call :scan_port %~1
if not "!PORT_PIDS!"==" " (
  echo [FAILED] Port %~1 is still in use, PID: !PORT_PIDS!
  exit /b 1
)
exit /b 0

:check_scheduler
REM Returns errorlevel 0 when a python process running app.scheduler exists.
REM The Name filter keeps this powershell call (whose command line also contains the text) from matching itself.
powershell -NoProfile -Command "if (@(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*app.scheduler*' }).Count -gt 0) { exit 0 } else { exit 1 }"
exit /b %errorlevel%

:scan_scheduler
REM Sets SCHED_PIDS to a space-padded PID list of running app.scheduler processes (" " = none).
set "SCHED_PIDS= "
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*app.scheduler*' } | ForEach-Object { $_.ProcessId }"`) do set "SCHED_PIDS=!SCHED_PIDS!%%P "
exit /b 0

:ensure_scheduler_free
REM Two schedulers on one database would raise every alert twice, so an old one must go first.
call :scan_scheduler
if "!SCHED_PIDS!"==" " exit /b 0
echo.
echo [NOTICE] An old scheduler is still running, PID: !SCHED_PIDS!
echo   Two schedulers at once would send every alert twice.
choice /c YN /n /m "Stop the old scheduler? [Y/N] "
if errorlevel 2 (
  echo Cancelled. Not starting a second copy.
  exit /b 1
)
for %%P in (!SCHED_PIDS!) do taskkill /PID %%P /F /T >nul 2>nul
call :sleep2
call :scan_scheduler
if not "!SCHED_PIDS!"==" " (
  echo [FAILED] Scheduler is still running, PID: !SCHED_PIDS!
  exit /b 1
)
exit /b 0
