@echo off
rem ============================================================
rem m-guard keepalive installer (r32 rewrite, r35 Qoder P1-2/P1-3/P2-2 fixes,
rem run as administrator).
rem History: R10.8 installed two SYSTEM scheduled tasks (m-guard-boot,
rem m-guard-watch-sys). Those were RETIRED on 09-26 (watchdog zombie case:
rem SYSTEM tasks + IgnoreNew ate every trigger; startup folder is the
rem one true keepalive now). This script used to resurrect them - that
rem is exactly what r32 reviews (Lyra P1 / CB F4 / Qoder P1#1) caught.
rem Now it only: 1) cleans up retired tasks, 2) locks dir ACL,
rem 3) starts the guard once for immediate use. Auto-start on boot =
rem the Startup-folder guard_boot.vbs (already installed per user).
rem r35 (Qoder P1-2): stale-kill switched to kill_guard.vbs (WMI CommandLine
rem match) - the old taskkill /im pythonw.exe + WINDOWTITLE filter matched
rem ZERO processes (real launcher is python.exe with no window title), so a
rem zombie guard on :9101 made step 4 print DONE while starting nothing.
rem r35 (Qoder P1-3): ACL grants %USERNAME% dynamically and checks the
rem return code instead of hardcoding one account name and silently
rem reporting DONE (icacls fails on any other machine = ACL NOT locked).
rem r35 (Qoder P2-2): also deletes the legacy \m-guard task - the XML
rem plan-B registered a third name this cleanup never covered.
rem ASCII-only: cmd.exe mis-parses UTF-8 Chinese.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click and choose "Run as administrator".
  pause
  exit /b 1
)
set "GUARDDIR=%~dp0"
echo [1/4] Removing retired watchdog tasks (idempotent)...
schtasks /Delete /tn m-guard-boot /f >nul 2>&1
schtasks /Delete /tn m-guard-watch-sys /f >nul 2>&1
schtasks /Delete /tn m-guard /f >nul 2>&1
echo [2/4] Killing stale guard processes (WMI CommandLine match via kill_guard.vbs)...
cscript //nologo "%GUARDDIR%kill_guard.vbs" 2>nul
echo [3/4] Locking guard dir ACL (deny Mia standard account)...
icacls "%GUARDDIR%" /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "%USERNAME%:(OI)(CI)F"
if errorlevel 1 (
  echo ERROR: ACL lock FAILED. Guard dir is NOT locked down - fix manually before trusting the containment model.
)
echo [4/4] Starting guard once (auto-restart on boot = Startup\guard_boot.vbs)...
cscript //nologo "%GUARDDIR%guard_boot.vbs"
timeout /t 4 /nobreak >nul
set "M_GUARD_PORT="
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_PORT=" "D:\m\.env" 2^>nul`) do set "M_GUARD_PORT=%%b"
if defined M_GUARD_PORT set "M_GUARD_PORT=%M_GUARD_PORT:~0,5%"
if not defined M_GUARD_PORT set "M_GUARD_PORT=9101"
if "%M_GUARD_PORT%"=="" set M_GUARD_PORT=9101
curl -s -m 5 http://127.0.0.1:%M_GUARD_PORT%/status
echo.
echo DONE. If nothing printed above, the guard did not come up - check D:\m\guard\ logs.
echo NOTE: keepalive on reboot = Startup folder VBS, NOT scheduled tasks.
pause
