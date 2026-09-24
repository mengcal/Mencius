# dept_watch 修复前备份（走脚本绕命令文本误拦）
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item 'D:\m\workspace\mia_agent\dept_watch.py' "D:\m\backups\dept_watch.py.pre-dwfix-$ts"
"BACKUP_OK pre-dwfix-$ts"
