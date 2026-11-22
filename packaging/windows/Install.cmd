@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "studioPy=%LocalAppData%\TalkingHeadStudio\python-3.13\python.exe"
if exist "%studioPy%" goto run
if "%STUDIO_BUNDLED_PYTHON%"=="1" goto install
for /f "delims=" %%P in ('where.exe python.exe 2^>nul ^| findstr.exe /I /V /C:"\WindowsApps\"') do (
  "%%P" -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)"
  if not errorlevel 1 (
    set "studioPy=%%P"
    goto run
  )
)
:install
echo Preparing Python for this workbench...
start "" /wait "%~dp0setup\python-3.13.14-amd64.exe" /passive InstallAllUsers=0 Include_launcher=0 PrependPath=0 AssociateFiles=0 Shortcuts=0 Include_test=0 "TargetDir=%LocalAppData%\TalkingHeadStudio\python-3.13"
if not exist "%studioPy%" goto failed
:run
"%studioPy%" -X utf8 "%~dp0setup\bootstrap.py" %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Installation did not finish. See the message above.
if not defined CI pause
exit /b 1
