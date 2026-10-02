@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title stock-desk dev-up

REM One-click launcher for stock-desk on Windows: git pull + backend + frontend.
REM Double-click it or run it from any directory; all paths derive from %~dp0.
REM Backend MUST start from its own directory so SQLite resolves to ./data/stock-desk.db.

set "TARGET_BRANCH=product/stock-desk"
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"

REM ---- 1. prerequisites ----
set "MISSING="
where git >nul 2>nul
if errorlevel 1 (
  echo [缺少] git，請到 https://git-scm.com/download/win 安裝
  set "MISSING=1"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo [缺少] uv，請到 https://docs.astral.sh/uv/getting-started/installation/ 安裝
  set "MISSING=1"
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [缺少] npm，請到 https://nodejs.org 安裝 Node.js
  set "MISSING=1"
)
if defined MISSING (
  echo 安裝後請重新開啟本程式。
  goto fail
)

set "HAVE_CURL="
where curl.exe >nul 2>nul
if not errorlevel 1 set "HAVE_CURL=1"

REM ---- 2. repo state checks ----
git -C "%REPO_ROOT%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [錯誤] 找不到 git repo：!REPO_ROOT!
  goto fail
)

REM Tracked changes only: untracked files do not block a fast-forward pull.
set "DIRTY="
for /f "delims=" %%L in ('git -C "%REPO_ROOT%" status --porcelain --untracked-files=no') do set "DIRTY=1"
if defined DIRTY (
  echo 你本機有改動，請先處理或告訴 Claude
  goto fail
)

set "CUR_BRANCH="
for /f "delims=" %%B in ('git -C "%REPO_ROOT%" rev-parse --abbrev-ref HEAD') do set "CUR_BRANCH=%%B"
if not "!CUR_BRANCH!"=="%TARGET_BRANCH%" (
  echo 目前分支是 !CUR_BRANCH!，不是 %TARGET_BRANCH%
  choice /c YN /n /m "要切換到 %TARGET_BRANCH% 嗎 [Y/N]？ "
  if errorlevel 2 (
    echo 已取消。
    goto fail
  )
  git -C "%REPO_ROOT%" checkout %TARGET_BRANCH%
  if errorlevel 1 (
    echo [錯誤] 切換分支失敗
    goto fail
  )
)

REM ---- 3. pull latest code ----
echo.
echo [1/4] 更新程式碼 git pull
git -C "%REPO_ROOT%" pull --ff-only origin %TARGET_BRANCH%
if errorlevel 1 (
  echo [錯誤] git pull 失敗，請把上面的訊息截圖給 Claude
  goto fail
)

REM ---- 4. stop old processes (before install, so Windows does not lock .venv / node_modules) ----
echo.
echo [2/4] 檢查舊程序 port 8000 / 3000
call :ensure_port_free 8000
if errorlevel 1 goto fail
call :ensure_port_free 3000
if errorlevel 1 goto fail

REM ---- 5. dependencies ----
echo.
echo [3/4] 安裝依賴
pushd "%BACKEND_DIR%"
uv sync --locked
if errorlevel 1 (
  popd
  echo [錯誤] 後端 uv sync 失敗
  goto fail
)
popd
pushd "%FRONTEND_DIR%"
REM npm is a .cmd file: it needs CALL, otherwise this script would stop after it.
call npm install --no-save
if errorlevel 1 (
  popd
  echo [錯誤] 前端 npm install 失敗
  goto fail
)
popd

REM ---- 6. start backend + frontend (each in its own window, kept open by /k) ----
echo.
echo [4/4] 啟動前後端
start "stock-desk 後端" cmd /k "cd /d "%BACKEND_DIR%" && uv run uvicorn app.main:app --reload --port 8000"
start "stock-desk 前端" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

REM ---- 7. wait for backend (max 60s) then frontend (max 90s) ----
echo 等待後端啟動，最多 60 秒...
set /a TRIES=0
:wait_backend
call :probe "http://localhost:8000/health"
if not errorlevel 1 goto backend_ok
set /a TRIES+=1
if !TRIES! GEQ 30 goto start_timeout
call :sleep2
goto wait_backend

:backend_ok
echo 後端已啟動，等待前端，最多 90 秒...
set /a TRIES=0
:wait_frontend
call :probe "http://localhost:3000"
if not errorlevel 1 goto frontend_ok
set /a TRIES+=1
if !TRIES! GEQ 45 goto start_timeout
call :sleep2
goto wait_frontend

:frontend_ok
REM Empty first quoted arg is the window title; otherwise start treats the URL as the title.
start "" "http://localhost:3000"
echo.
echo 完成。
echo 要停止：關掉兩個 stock-desk 視窗即可。
echo 網址：http://localhost:3000
echo.
pause
exit /b 0

:start_timeout
echo.
echo 後端／前端沒有在時間內啟動，請看「stock-desk 後端」視窗的錯誤訊息
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
echo [注意] port %~1 已被占用：
for %%P in (!PORT_PIDS!) do (
  if "%%P"=="4" (
    echo   PID 4 是 Windows 系統程序，無法結束；請改用其他 port 或重開機後再試。
    exit /b 1
  )
  for /f "tokens=1" %%N in ('tasklist /FI "PID eq %%P" /NH') do echo   PID %%P：%%N
)
choice /c YN /n /m "要結束舊程序嗎 [Y/N]？ "
if errorlevel 2 (
  echo 已取消，不會啟動第二份。
  exit /b 1
)
for %%P in (!PORT_PIDS!) do taskkill /PID %%P /F /T
call :sleep2
call :scan_port %~1
if not "!PORT_PIDS!"==" " (
  echo [失敗] port %~1 仍被占用，PID：!PORT_PIDS!
  exit /b 1
)
exit /b 0
