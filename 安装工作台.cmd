@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 scripts\install_app.py %*
if errorlevel 1 (
  pause
  exit /b 1
)
