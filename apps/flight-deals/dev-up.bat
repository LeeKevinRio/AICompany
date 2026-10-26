@echo off
setlocal enabledelayedexpansion
title flight-deals dev-up

REM One-click launcher for flight-deals on Windows: git pull + uv sync + single server process.
REM Double-click it or run it from any directory; all paths derive from %~dp0.
REM The app is ONE process (web + APScheduler + SQLite). Never add --reload or extra workers: that creates two schedulers.
REM The app reads apps\flight-deals\.env by itself, so this script does not load any environment variables.

set "TARGET_BRANCH=product/flight-deals"
set "PORT=8795"
for %%I in ("%~dp0.") do set "APP_DIR=%%~fI"
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
if defined MISSING (
  echo After installing, run this script again.
  goto fail
)

set "HAVE_CURL="
where curl.exe >nul 2>nul
if not errorlevel 1 set "HAVE_CURL=1"

if not exist "%APP_DIR%\.env" echo [NOTICE] .env not found; Telegram notifications stay off until you create it (see README)
if exist "%APP_DIR%\.env" findstr /B /C:"FLIGHT_DEALS_PORT" "%APP_DIR%\.env" >nul && echo [NOTICE] .env sets FLIGHT_DEALS_PORT; this script always uses port %PORT% and passes --port %PORT% explicitly

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
  if not "!errorlevel!"=="1" (
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
REM A missing remote branch (before the first push) or being offline is NOT a failure: keep using local code.
git -C "%REPO_ROOT%" ls-remote --exit-code --heads origin %TARGET_BRANCH% >nul 2>nul
if errorlevel 1 (
  echo [SKIP] Remote branch origin/%TARGET_BRANCH% not reachable or not pushed yet; using local code.
) else (
  git -C "%REPO_ROOT%" pull --ff-only origin %TARGET_BRANCH%
  if errorlevel 1 (
    echo [ERROR] git pull failed - please send a screenshot of the messages above to Claude
    goto fail
  )
)

REM ---- 4. stop old processes (before install, so Windows does not lock .venv) ----
echo.
echo [2/4] Checking for an old server on port %PORT% and for an old flight-deals process
call :ensure_port_free %PORT%
if errorlevel 1 goto fail
call :ensure_app_free
if errorlevel 1 goto fail

REM ---- 5. dependencies ----
echo.
echo [3/4] Installing dependencies
pushd "%APP_DIR%"
uv sync --locked
if errorlevel 1 (
  popd
  echo [ERROR] uv sync failed
  goto fail
)
popd

REM ---- 6. start the single process in its own window kept open by /k ----
echo.
echo [4/4] Starting flight-deals
start "flight-deals" cmd /k "cd /d "%APP_DIR%" && uv run flight-deals --port %PORT%"

REM ---- 7. wait for the home page (max 60s) ----
echo Waiting for http://127.0.0.1:%PORT%/ (up to 60 seconds)...
set /a TRIES=0
:wait_app
call :probe "http://127.0.0.1:%PORT%/"
if not errorlevel 1 goto app_ok
set /a TRIES+=1
if !TRIES! GEQ 30 goto app_timeout
call :sleep2
goto wait_app

:app_ok
echo.
echo [OK] flight-deals http://127.0.0.1:%PORT%
REM Empty first quoted arg is the window title; otherwise start treats the URL as the title.
start "" "http://127.0.0.1:%PORT%"
echo.
echo Done.
echo To stop: close the 'flight-deals' window.
echo URL: http://127.0.0.1:%PORT%
echo.
pause
exit /b 0

:app_timeout
echo.
echo [FAIL] flight-deals did not answer at http://127.0.0.1:%PORT% in time.
echo Check the error in the 'flight-deals' window and send a screenshot to Claude.
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
REM Last 5 chars of the address are compared, so :87950 and :18795 never match :8795.
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
if not "!errorlevel!"=="1" (
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

:scan_app
REM Sets APP_PIDS to a space-padded PID list of running flight-deals python processes (launched via flight-deals.exe or -m flight_deals) (" " = none).
REM The Name filter keeps this powershell call (whose command line also contains the text) from matching itself.
set "APP_PIDS= "
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*flight-deals.exe*' -or $_.CommandLine -like '*-m flight_deals*') } | ForEach-Object { $_.ProcessId }"`) do set "APP_PIDS=!APP_PIDS!%%P "
exit /b 0

:ensure_app_free
REM Two copies would each run a scheduler and scan the same watches twice, so an old one must go first.
call :scan_app
if "!APP_PIDS!"==" " exit /b 0
echo.
echo [NOTICE] An old flight-deals process is still running, PID: !APP_PIDS!
REM Show a truncated command line per PID so the user can see what will be stopped.
for %%P in (!APP_PIDS!) do powershell -NoProfile -Command "$c = (Get-CimInstance Win32_Process -Filter 'ProcessId=%%P').CommandLine; if ($c) { '  PID %%P: ' + $c.Substring(0, [Math]::Min(120, $c.Length)) }"
echo   Two copies at once would scan every watch twice.
choice /c YN /n /m "Stop the old flight-deals process? [Y/N] "
if not "!errorlevel!"=="1" (
  echo Cancelled. Not starting a second copy.
  exit /b 1
)
for %%P in (!APP_PIDS!) do taskkill /PID %%P /F /T >nul 2>nul
call :sleep2
call :scan_app
if not "!APP_PIDS!"==" " (
  echo [FAILED] flight-deals is still running, PID: !APP_PIDS!
  exit /b 1
)
exit /b 0
