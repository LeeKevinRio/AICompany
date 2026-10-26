@echo off
setlocal
title flight-deals uninstall-autostart

REM Removes the per-user login autostart entry (HKCU Run key). No admin rights, no secrets.
REM All paths derive from %~dp0, so it works from any directory.

where uv >nul 2>nul
if errorlevel 1 goto no_uv

uv run --project "%~dp0." flight-deals autostart uninstall
set "RC=%errorlevel%"
echo.
echo Exit code: %RC%
echo.
pause
exit /b %RC%

:no_uv
echo [MISSING] uv - install from https://docs.astral.sh/uv/getting-started/installation/
goto fail

:fail
echo.
pause
exit /b 1
