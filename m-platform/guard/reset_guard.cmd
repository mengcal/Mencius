@echo off
rem ============================================================
rem m-guard RESET (R10.408) - last-resort recovery
rem Use when: admin password forgotten AND browser cookie lost.
rem Effect: wipes key+password. Platform returns to the setup
rem         wizard, where a new username+password can be claimed.
rem Note:   the old .token_bootstrap activation-code mechanism is
rem         retired (Dad 09-23: no lock before registration).
rem Run: right-click -> "Run as administrator".
rem ASCII-only: cmd.exe mis-parses UTF-8 Chinese.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click and choose "Run as administrator".
  pause
  exit /b 1
)
echo This will WIPE the admin key and password. The platform
echo returns to the setup wizard: whoever registers first owns it.
choice /C YN /M "Confirm reset"
if %errorlevel% neq 1 exit /b 1
del /f /q "%~dp0token.bin" 2>nul
del /f /q "%~dp0password.bin" 2>nul
del /f /q "%~dp0hostcopy.token" 2>nul
del /f /q "%~dp0.token_bootstrap" 2>nul
rem r31 09-26: m-guard-watch-sys task retired - guard auto-restarts via Startup folder
timeout /t 4 /nobreak >nul
set "M_GUARD_PORT="
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_PORT=" "D:\m\.env" 2^>nul`) do set "M_GUARD_PORT=%%b"
if defined M_GUARD_PORT set "M_GUARD_PORT=%M_GUARD_PORT:~0,5%"
if not defined M_GUARD_PORT set "M_GUARD_PORT=9101"
if "%M_GUARD_PORT%"=="" set M_GUARD_PORT=9101
curl -s -m 5 http://127.0.0.1:%M_GUARD_PORT%/status
echo.
echo DONE. Refresh the platform page - the setup wizard will appear.
pause
