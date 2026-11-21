@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "STUDIO_PYTHON=python"
if exist "..\runtime\Scripts\python.exe" set "STUDIO_PYTHON=..\runtime\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "STUDIO_PYTHON=.venv\Scripts\python.exe"
"%STUDIO_PYTHON%" -X utf8 scripts\launch.py %*
if errorlevel 1 (
  pause
  exit /b 1
)
