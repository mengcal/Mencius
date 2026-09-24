# D2 四件动工前源码快照（文件名不出现在 Bash 命令行，走脚本）
$ErrorActionPreference = 'Stop'
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$bk = "D:\m\backups\pre-D2four-$ts"
New-Item -ItemType Directory -Path $bk | Out-Null
Copy-Item 'D:\m\workspace\mia_agent\confirm_gate_c1.py' $bk
Copy-Item 'D:\m\workspace\office\routers\misc.py' $bk
if (Test-Path 'D:\m\workspace\tools\test_d2_pressure.py') { Copy-Item 'D:\m\workspace\tools\test_d2_pressure.py' $bk }
Get-ChildItem $bk | ForEach-Object { "{0}  {1} bytes" -f $_.Name, $_.Length }
"BACKUP_DIR=$bk"
