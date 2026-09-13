# dev-restart.ps1 — 前端 dev:3000 僵尸清理+缓存重置+分离重启（turbopack 假死/全404 时用）
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File D:\m\tools\dev-restart.ps1
$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match 'deep-agents-ui' }
foreach ($p in $procs) {
  Write-Output ("KILL " + $p.ProcessId)
  Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3
if (Test-Path 'D:\m\deep-agents-ui\.next') {
  Remove-Item -Recurse -Force 'D:\m\deep-agents-ui\.next' -ErrorAction SilentlyContinue
  Write-Output 'CLEARED .next'
}
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev > D:\m\dev-3000.log 2>&1" -WorkingDirectory "D:\m\deep-agents-ui" -WindowStyle Hidden
Write-Output 'DEV STARTED (detached) — 冷启动编译约 60-90s'
