@echo off
setlocal
title stock-desk cg2-preflight

REM One-click CG-2 read-only preflight: a thin launcher. All logic lives in
REM backend\scripts\cg2_register.py (ADR-0030 supplement 4 point 4).
REM The script runs the CG-2 checks and stops (read-only); this launcher never
REM updates the code. Paths derive from the folder of this file (%~dp0).

REM Do not let uv load any .env file into the process environment.
set "UV_ENV_FILE="

set "APP_DIR=%~dp0"
set "BACKEND_DIR=%APP_DIR%backend"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
  echo After installing, run this script again.
  goto fail
)

cd /d "%BACKEND_DIR%"
if errorlevel 1 (
  echo [ERROR] Cannot find the backend folder next to this file.
  goto fail
)

uv run --no-sync python -I -X utf8 scripts\cg2_register.py preflight
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.
pause
exit /b %RC%

:fail
echo.
pause
exit /b 1
