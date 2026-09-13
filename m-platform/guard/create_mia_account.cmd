@echo off
rem ============================================================
rem Create dedicated standard account for Mia (R10.6c, 2026-09-06)
rem Right-click -> "Run as administrator", wait for DONE lines.
rem ASCII-only: cmd.exe mis-parses UTF-8 Chinese.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Please right-click and choose "Run as administrator".
  pause
  exit /b 1
)
net user mia 3Yg2AlY_8HK4PMZDkf0 /add /fullname:"Mia Service Account" /comment:"M-Platform service account - standard user, no admin" /expires:never /y
if %errorlevel% neq 0 (
  echo FAILED to create user mia. Maybe it already exists - that is fine.
) else (
  echo User mia created (standard user, NOT in Administrators).
)
rem Double-lock the secrets folder: explicit deny for mia (deny beats allow)
icacls "D:\m\secrets" /deny "mia:(OI)(CI)(F)"
rem Guard folder: deny mia too
icacls "D:\m\guard" /deny "mia:(OI)(CI)(F)"
echo.
echo DONE. Account mia ready (standard user). Password stored in
echo D:\glm\projects\notes\secrets\mia_account.md - keep private.
pause
