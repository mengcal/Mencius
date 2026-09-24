"""m-guard Windows service wrapper (r30, 09-24).

Dad's order: retire the minute-polling watchdog task ("烦人") — follow the
ZCode doctrine: no hand-rolled watchdog; let the OS service controller (SCM)
own process liveness. SCM recovery policy = crash self-restart, services
never draw a window, zero polling.

Design (audited core untouched):
- This service process spawns `python.exe m_guard.py` as a child (same
  interpreter + same absolute paths as run_guard.cmd) and waits on it.
- Unexpected child exit  -> service exits non-zero WITHOUT reporting STOPPED
  -> SCM treats it as a failure -> recovery action restarts it (60 s).
- Proper service stop   -> we terminate the child ourselves, report STOPPED,
  exit 0 -> SCM does not restart.
- Before spawning, kill stale guards via kill_guard.vbs (WMI CommandLine
  match) so a leftover from the retired tasks can't squat on port 9101.

Install/start/recovery are done by the admin one-click
(celia-work/retire-watchdog-0924.ps1), not here.
"""
import os
import subprocess
import sys

import pythoncom
import servicemanager
import win32event
import win32service
import win32serviceutil

GUARD_DIR = r"D:\m\guard"
PYTHON_EXE = r"C:\Users\wolfm\.pyenv\pyenv-win\versions\3.12.0\python.exe"
GUARD_PY = os.path.join(GUARD_DIR, "m_guard.py")
KILL_VBS = os.path.join(GUARD_DIR, "kill_guard.vbs")
CRASH_LOG = os.path.join(GUARD_DIR, "guard_crash.log")
CREATE_NO_WINDOW = 0x08000000


class MGuardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "m-guard"
    _svc_display_name_ = "M Platform Guard (m-guard)"
    _svc_description_ = (
        "M 平台令牌/密码守卫（127.0.0.1:9101）。崩溃由 SCM 恢复策略自动拉起，"
        "替代原每分钟计划任务看门狗（r30 退役）。"
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.proc = None
        self.stopping = False

    def _log(self, msg):
        try:
            servicemanager.LogInfoMsg("m-guard: " + msg)
        except Exception:
            pass

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stopping = True
        win32event.SetEvent(self.stop_event)
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    def SvcDoRun(self):
        pythoncom.CoInitialize()
        # 清场：掐掉任何残留守卫（旧任务/旧服务留下的），再独占 9101。
        try:
            subprocess.run(
                ["cscript", "//nologo", KILL_VBS],
                timeout=20, creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            self._log("pre-kill failed: %r" % e)
        try:
            log = open(CRASH_LOG, "a", encoding="utf-8", errors="replace")
            self.proc = subprocess.Popen(
                [PYTHON_EXE, GUARD_PY],
                cwd=GUARD_DIR, stdout=log, stderr=log,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            self._log("spawn failed: %r" % e)
            rc = 1
        else:
            rc = self.proc.wait()
        if self.stopping:
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)
            return
        # 意外死亡：不报 STOPPED，非零退出 -> SCM failure -> restart。
        self._log("guard exited rc=%s; failing service for SCM restart" % rc)
        os._exit(rc or 1)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(MGuardService)
