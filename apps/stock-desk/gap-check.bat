@echo off
setlocal
title stock-desk gap-check

REM One-click off-ledger missing-day comparison: a thin launcher. All logic lives in
REM backend\scripts\gap_check.py (ADR-0030 supplement 8 point 5).
REM The script copies the database with the SQLite backup API and reads only the copy; this
REM launcher never updates the code. Paths derive from the folder of this file (%~dp0).

REM Do not let uv load any .env file into the process environment.
set "UV_ENV_FILE="

set "APP_DIR=%~dp0"
set "BACKEND_DIR=%APP_DIR%backend"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MISSING] uv was not found. Do not install or update anything yourself.
  echo Tell the coordinator.
  goto fail
)

cd /d "%BACKEND_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find the backend folder next to this file.
  goto fail
)

uv run --no-sync python -I -X utf8 scripts\gap_check.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.
pause
exit /b %RC%

:fail
echo.
pause
exit /b 1
