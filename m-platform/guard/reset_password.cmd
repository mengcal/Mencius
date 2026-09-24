@echo off
chcp 65001 >nul
rem ============================================================
rem reset_password.cmd - 09-17 OWUI 颗粒度对齐（爸爸令：忘记密码不该归零设置）
rem 只改管理员密码：证明=本机能读 guard 目录与 .env（物理访问即信任锚，
rem 同 .token_bootstrap 的语义）。密钥/设置/对话零改动。
rem reset_guard.cmd 仍是"全部重置"核弹（清密钥+密码+回注册向导），两者分开。
rem ============================================================
set GK=
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Select-String -Path 'D:\m\.env' -Pattern '^M_GUARD_KEY=(.+)$').Matches[0].Groups[1].Value"`) do set GK=%%a
if "%GK%"=="" (
    echo [错误] 读不到 D:\m\.env 的 M_GUARD_KEY
    pause & exit /b 1
)
set HC=
for /f "usebackq delims=" %%a in (`type "D:\m\guard\hostcopy.token"`) do set HC=%%a
if "%HC%"=="" (
    echo [错误] 读不到 D:\m\guard\hostcopy.token（若刚全清过，请先走注册向导）
    pause & exit /b 1
)
echo 将修改 M 平台管理员密码（设置与对话不动）。
set NEW=
set /p NEW=输入新管理员密码（至少 8 位；会显示在屏幕上，本机无旁观即可）:
if "%NEW%"=="" ( echo 已取消。 & exit /b 0 )
curl -s -m 8 -X POST http://127.0.0.1:9101/set_password -H "Content-Type: application/json" -H "X-Guard-Key: %GK%" -d "{\"password\":\"%NEW%\",\"current\":\"%HC%\"}"
echo.
echo 上面返回 {"ok": true} 即改密成功，用新密码登录即可。
pause
