@echo off
setlocal
title stock-desk r2-probe

REM One-click R2 probe: a thin launcher. All logic lives in backend\scripts\r2_first_run.py.
REM The script copies the database and only reads the copy; this launcher never updates the code.
REM Paths derive from the folder of this file (%~dp0), so it can be double-clicked from anywhere.

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

uv run --no-sync python -I -X utf8 scripts\r2_first_run.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [NOTE] The tool ended with code %RC%. Read the messages above.
pause
exit /b %RC%

:fail
echo.
pause
exit /b 1
