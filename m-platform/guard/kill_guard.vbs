' kill_guard.vbs - terminate stale m_guard processes only (R10.439/09-24).
' Match: image python.exe/pythonw.exe AND command line containing m_guard.py.
' Replaces the powershell Get-CimInstance one-liner (window-flash culprit) and
' the removed wmic. WMI scripting is built into the OS; cscript inherits the
' hidden console of its caller, so this stays invisible under the wscript
' wrapper chain. Never touches unrelated python processes.
On Error Resume Next
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set ps = wmi.ExecQuery( _
  "SELECT * FROM Win32_Process WHERE (Name='python.exe' OR Name='pythonw.exe') AND CommandLine LIKE '%m_guard.py%'")
For Each p In ps
  p.Terminate
Next
If Err.Number <> 0 Then WScript.Quit 1
WScript.Quit 0
