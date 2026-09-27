@echo off
chcp 65001 >nul
rem ============================================================
rem reset_password.cmd - 09-17 OWUI 颗粒度对齐（爸爸令：忘记密码不该归零设置）
rem 只改管理员密码：证明=本机能读 guard 目录与 .env（物理访问即信任锚，
rem 同 .token_bootstrap 的语义）。密钥/设置/对话零改动。
rem reset_guard.cmd 仍是"全部重置"核弹（清密钥+密码+回注册向导），两者分开。
rem r35（Qoder P1-1）补齐三缺件——修前这条爸爸被告知唯一找回通道必然失败：
rem   1) GK 读取行（R10.11 给 /set_password 加了 X-Guard-Key 门，旧版空头=403）；
rem   2) NEW 密码提示输入（旧版从未赋值=400"密码至少 8 位"）；
rem   3) HC 读 hostcopy.token 作 current（m_guard :419-422 契约"带 hostcopy 作
rem      current"——旧版 %HC% 根本不存在）。
rem 建议密码避开英文引号与 & 符号（cmd 传参形态所限）。
rem ============================================================
set GK=
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_KEY=" "D:\m\.env" 2^>nul`) do set GK=%%b
if "%GK%"=="" (
  echo 错误：D:\m\.env 里没读到 M_GUARD_KEY，无法向守卫证明宿主身份，已中止（什么都没改）。
  pause
  exit /b 1
)
set "M_GUARD_PORT="
for /f "usebackq tokens=1* delims==" %%a in (`findstr /b "M_GUARD_PORT=" "D:\m\.env" 2^>nul`) do set "M_GUARD_PORT=%%b"
if defined M_GUARD_PORT set "M_GUARD_PORT=%M_GUARD_PORT:~0,5%"
if not defined M_GUARD_PORT set "M_GUARD_PORT=9101"
if "%M_GUARD_PORT%"=="" set M_GUARD_PORT=9101
set HC=
if exist "D:\m\guard\hostcopy.token" set /p HC=<"D:\m\guard\hostcopy.token"
if "%HC%"=="" (
  echo 错误：读不到 D:\m\guard\hostcopy.token（守卫从未导出当前密钥副本），无法证明改密资格，已中止。
  echo 若已彻底无法登录且确要归零，才用 reset_guard.cmd（清密钥+密码+回注册向导）。
  pause
  exit /b 1
)
set NEW=
set /p NEW=请输入新管理员密码（至少 8 位，输入会显示在屏幕上）:
if "%NEW%"=="" (
  echo 错误：密码为空，已中止（什么都没改）。
  pause
  exit /b 1
)
curl -s -m 8 -X POST http://127.0.0.1:%M_GUARD_PORT%/set_password -H "Content-Type: application/json" -H "X-Guard-Key: %GK%" -d "{\"password\":\"%NEW%\",\"current\":\"%HC%\"}"
echo.
echo 上面返回 {"ok": true} 即改密成功，用新密码登录即可。
pause
