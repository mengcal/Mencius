@echo off
chcp 65001 >nul
rem ============================================================
rem reset_password.cmd - 09-17 OWUI 颗粒度对齐（爸爸令：忘记密码不该归零设置）
rem 只改管理员密码：证明=本机能读 guard 目录与 .env（物理访问即信任锚，
rem 同 .token_bootstrap 的语义）。密钥/设置/对话零改动。
rem reset_guard.cmd 仍是"全部重置"核弹（清密钥+密码+回注册向导），两者分开。
rem ============================================================
set GK=
set "M_GUARD_PORT="
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_PORT=" "D:\m\.env" 2^>nul`) do set "M_GUARD_PORT=%%b"
if defined M_GUARD_PORT set "M_GUARD_PORT=%M_GUARD_PORT:~0,5%"
if not defined M_GUARD_PORT set "M_GUARD_PORT=9101"
if "%M_GUARD_PORT%"=="" set M_GUARD_PORT=9101
curl -s -m 8 -X POST http://127.0.0.1:%M_GUARD_PORT%/set_password -H "Content-Type: application/json" -H "X-Guard-Key: %GK%" -d "{\"password\":\"%NEW%\",\"current\":\"%HC%\"}"
echo.
echo 上面返回 {"ok": true} 即改密成功，用新密码登录即可。
pause
