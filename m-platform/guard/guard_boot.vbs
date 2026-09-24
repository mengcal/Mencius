' guard_boot.vbs - silent guard launcher at logon (r30, 09-24).
' Hidden console, wait=True: this script lives as long as the guard does.
' run_guard.cmd has its own double-start probe, so racing the leftover SYSTEM
' task is harmless. ASCII-only comments (GBK codepage lesson batch).
CreateObject("WScript.Shell").Run "cmd /c D:\m\guard\run_guard.cmd", 0, True
