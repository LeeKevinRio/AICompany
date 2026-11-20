@echo off
setlocal
title stock-desk forecast-status

REM One-click forecast status report: a thin launcher. All logic lives in
REM backend\scripts\forecast_status.py (ADR-0030 supplement 11 points 2 and 4).
REM The script only reads the main database (no copy, no write); this launcher never
REM updates the code. Paths derive from the folder of this file (%~dp0).

REM Do not let uv load any .env file into the process environment.
set "UV_ENV_FILE="

set "APP_DIR=%~dp0"
set "BACKEND_DIR=%APP_DIR%backend"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
  echo Tell the coordinator.
  goto fail
)

cd /d "%BACKEND_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find the backend folder next to this file.
  goto fail
)

uv run --no-sync python -I -X utf8 scripts\forecast_status.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.
pause
exit /b %RC%

:fail
echo.
pause
exit /b 1
