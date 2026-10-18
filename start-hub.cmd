@echo off
rem agent-hub launcher (Windows). Double-click to start and open the console.
setlocal
set "ROOT=%~dp0"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8765"
set "HUB_NO_BROWSER="
set "PYTHONIOENCODING=utf-8"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%start-hub.ps1" -Port %PORT%
endlocal
