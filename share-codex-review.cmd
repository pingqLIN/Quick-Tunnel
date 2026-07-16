@echo off
setlocal

where pwsh.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: PowerShell 7 ^(pwsh.exe^) is required.
  pause
  exit /b 1
)

if "%~1"=="" (
  set /p "TARGET=Folder to share: "
) else (
  set "TARGET=%~1"
)

if not defined TARGET (
  echo No folder selected.
  pause
  exit /b 1
)

pwsh.exe -NoLogo -NoProfile -File "%~dp0share-codex-review.ps1" "%TARGET%" -WaitForAcknowledgement
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" pause
exit /b %RESULT%
