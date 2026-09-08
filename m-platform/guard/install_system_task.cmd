@echo off
rem ============================================================
rem m-guard SYSTEM install (R10.8) - run as administrator.
rem 1) Kill any stale guard processes (old code keeps port 9101).
rem 2) Lock the guard directory ACL (SYSTEM+Administrators+%USERNAME%).
rem 3) (Re)install SYSTEM tasks and start the guard with current code.
rem ASCII-only: cmd.exe mis-parses UTF-8 Chinese.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click and choose "Run as administrator".
  pause
  exit /b 1
)
echo [1/3] Killing stale guard processes...
taskkill /f /im pythonw.exe 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq m_guard*" 2>nul
echo [2/3] Locking guard directory ACL (deny agent standard account)...
icacls "%~dp0." /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "%USERNAME%:(OI)(CI)F"
echo [3/3] Installing SYSTEM tasks...
schtasks /Create /tn m-guard-boot /sc onstart /ru SYSTEM /tr "cmd /c %~dp0ensure_guard.cmd" /f
schtasks /Create /tn m-guard-watch-sys /sc minute /mo 1 /ru SYSTEM /tr "cmd /c %~dp0ensure_guard.cmd" /f
schtasks /Run /tn m-guard-watch-sys
timeout /t 4 /nobreak >nul
curl -s -m 5 http://127.0.0.1:9101/status
echo.
echo DONE. Refresh the platform page - the setup wizard will appear.
echo Activation code file: %~dp0.token_bootstrap
pause
