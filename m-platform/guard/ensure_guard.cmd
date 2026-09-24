@echo off
rem m-guard keep-alive (R10.8h / 09-24 r30 quiescence): SYSTEM task, every minute + at boot.
rem Probe: keyed POST /verify with a wrong token must return 200 {"ok":false}
rem (KEY matches -> new code alive). 000/403/other -> DEAD -> kill stale guard
rem (matched by command line via WMI, NOT image name) and start fresh.
rem
rem 09-24 r30 (Dad: "watchdog keeps flashing a black window, ruins my mood"):
rem   ALL powershell.exe removed from this chain. Empirically (09-23 ledger:
rem   "WT powershell residue"), powershell launched from this hidden-console
rem   chain still spawns a visible Windows Terminal window on this box, up to
rem   3 flashes per minute. Replacements:
rem     - env key read : findstr (pure cmd)
rem     - health probe : curl -w http_code (curl 8.21 on PATH)
rem     - stale kill   : cscript kill_guard.vbs (WMI CommandLine match;
rem                      wmic itself is GONE from this OS build 26200)
rem   cscript/cmd/curl inherit the hidden console created by ensure_guard.vbs
rem   (Run style 0) -> zero visible windows.
rem NOTE: this whole task is being RETIRED by the m-guard Windows service
rem   (SCM recovery strategy replaces minute-polling). Kept working until then.
rem History: 09-17 removed -SkipHttpErrorCheck (PS5.1 has no such param ->
rem   probe always threw -> 11995 needless restarts in 11 days).
set GK=
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_KEY=" "D:\m\.env"`) do set GK=%%b
if "%GK%"=="" goto restart
set PROBE=
for /f "usebackq delims=" %%a in (`curl -s -o NUL -w "%%{http_code}" -m 3 -X POST -H "Content-Type: application/json" -H "X-Guard-Key: %GK%" -d "{\"token\":\"probe-x\"}" http://127.0.0.1:9101/verify`) do set PROBE=%%a
if "%PROBE%"=="200" exit /b 0
:restart
cscript //nologo "D:\m\guard\kill_guard.vbs"
start "" /b "D:\m\guard\run_guard.cmd"
exit /b 0
