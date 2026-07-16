@echo off
setlocal

where pwsh.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: PowerShell 7 ^(pwsh.exe^) is required.
  pause
  exit /b 1
)

echo.
echo Codex Review context menu
echo   1. Install
echo   2. Remove
echo   3. Show status
echo   4. Cancel
echo.
choice /c 1234 /n /m "Select [1-4]: "

if errorlevel 4 goto :cancel
if errorlevel 3 goto :status
if errorlevel 2 goto :remove

:install
pwsh.exe -NoLogo -NoProfile -File "%~dp0manage-context-menu.ps1" -Action Install
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

:remove
pwsh.exe -NoLogo -NoProfile -File "%~dp0manage-context-menu.ps1" -Action Uninstall
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

:status
pwsh.exe -NoLogo -NoProfile -File "%~dp0manage-context-menu.ps1" -Action Status
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

:cancel
exit /b 0
