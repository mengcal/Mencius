@echo off
rem m-guard keep-alive (R10.8h): SYSTEM task, every minute + at boot.
rem Probe: keyed POST /verify with a wrong token must return 200 {"ok":false}
rem (KEY matches -> new code alive). 403=KEY mismatch/stale guard, no response=
rem dead -> kill stale pythonw (matched by command line, not image name) and
rem start fresh with current code.
set GK=
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Select-String -Path 'D:\m\.env' -Pattern '^M_GUARD_KEY=(.+)$').Matches[0].Groups[1].Value"`) do set GK=%%a
if "%GK%"=="" goto restart
set PROBE=
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9101/verify' -Method Post -ContentType 'application/json' -Body '{\"token\":\"probe-x\"}' -Headers @{ 'X-Guard-Key' = '%GK%' } -TimeoutSec 3 -SkipHttpErrorCheck; $r.StatusCode } catch { 'DEAD' }" 2^>NUL`) do set PROBE=%%a
if "%PROBE%"=="200" exit /b 0
:restart
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*D:\m\guard\m_guard.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
start "" /b "%USERPROFILE%\.pyenv\pyenv-win\versions\3.12.0\pythonw.exe" "D:\m\guard\m_guard.py"
exit /b 0
