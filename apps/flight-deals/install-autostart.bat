@echo off
setlocal
title flight-deals install-autostart

REM Installs the per-user login autostart entry (HKCU Run key). No admin rights, no secrets.
REM All paths derive from %~dp0, so it works from any directory.

where uv >nul 2>nul
if errorlevel 1 goto no_uv
if not exist "%~dp0.venv\Scripts\pythonw.exe" goto no_venv

uv run --project "%~dp0." flight-deals autostart install
set "RC=%errorlevel%"
echo.
echo Exit code: %RC%
echo.
pause
exit /b %RC%

:no_uv
echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
goto fail

:no_venv
echo [MISSING] .venv\Scripts\pythonw.exe in this folder
echo Run dev-up.bat once first to create the virtual environment, then run this script again.
goto fail

:fail
echo.
pause
exit /b 1
