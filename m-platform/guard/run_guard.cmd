@echo off
rem run_guard.cmd - guard launcher (r27): python.exe with console redirect so
rem crash reasons land in guard_crash.log (pythonw silent death was the worst
rem obstacle in that debug session).
rem r30 double-start guard: if 9101 already answers, exit clean (0) - the
rem leftover SYSTEM task and the Startup-folder vbs must never fight a live
rem guard for the port.
rem 09-24: comments ASCII-only (GBK codepage mangles UTF-8 Chinese comments
rem into fake commands on boot - same lesson as litellm-gw.bat).
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "try{(Select-String -Path 'D:\m\.env' -Pattern '^M_GUARD_PORT=(.+)$').Matches[0].Groups[1].Value}catch{''}"`) do set M_GUARD_PORT=%%a
if "%M_GUARD_PORT%"=="" set M_GUARD_PORT=9101
curl -s -o NUL -m 2 http://127.0.0.1:%M_GUARD_PORT%/status && exit /b 0
"C:\Users\wolfm\.pyenv\pyenv-win\versions\3.12.0\python.exe" "D:\m\guard\m_guard.py" >> "D:\m\guard\guard_crash.log" 2>&1
