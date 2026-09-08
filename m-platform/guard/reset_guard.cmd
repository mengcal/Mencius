@echo off
rem ============================================================
rem m-guard RESET (R10.7b) - last-resort recovery
rem Use when: admin password forgotten AND browser cookie lost.
rem Effect: wipes key+password, regenerates activation code,
rem         platform returns to first-time setup (setup wizard).
rem Run: right-click -> "Run as administrator".
rem ASCII-only: cmd.exe mis-parses UTF-8 Chinese.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click and choose "Run as administrator".
  pause
  exit /b 1
)
echo This will WIPE the admin key and password, then regenerate
echo the activation code. Platform returns to setup wizard.
choice /C YN /M "Confirm reset"
if %errorlevel% neq 1 exit /b 1
del /f /q "%~dp0token.bin" 2>nul
del /f /q "%~dp0password.bin" 2>nul
del /f /q "%~dp0hostcopy.token" 2>nul
del /f /q "%~dp0.token_bootstrap" 2>nul
schtasks /Run /tn m-guard-watch-sys >nul 2>&1
timeout /t 4 /nobreak >nul
curl -s -m 5 http://127.0.0.1:9101/status
echo.
echo DONE. Open %~dp0.token_bootstrap for the new activation code,
echo then refresh the platform page - the setup wizard will appear.
pause
