' ensure_guard.vbs — 看门狗静默包装（r27 后续，爸爸 09-24 00:5x 报每分钟弹 cmd 窗口碍事）
' wscript 以窗口样式 0（隐藏）拉起 ensure_guard.cmd，cmd 及其子进程共享这个隐形控制台，
' 从此每分钟巡检不再闪窗。任务动作由一键件第3步换成：wscript.exe //B D:\m\guard\ensure_guard.vbs
CreateObject("WScript.Shell").Run "cmd /c D:\m\guard\ensure_guard.cmd", 0, False
