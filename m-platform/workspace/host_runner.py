# -*- coding: utf-8 -*-
# r36k（09-28 爸令完整分区）：本 runner 是「宿主机工作区」的执行后端——对话里选宿主域才走它；
# 档位不开后门（路由见 mia_agent/sandbox.py _route）；Startup 自启件 m-host-runner.vbs 已恢复。
r"""host_runner.py —— 米娅"完全访问档"的宿主执行后端（09-17 深夜爸爸定纲：米娅=知夏同等权限）

语义：general.confirmLevel == "full" 时，米娅的 execute 经此服务落在宿主 Git Bash
（与知夏同款 shell、同款权限）；其他档位本服务直接 403（沙箱路线不变）。
信任模型：完全访问=爸爸拨的信任档，代价与知夏对等——被注入的米娅能干什么，
这个 runner 就能干什么；绝对红线（银行/支付/转账）是智能体纪律层，不归本服务执法。

安全护栏（本服务自身）：
- 只绑 127.0.0.1:2026（宿主回环，不出机器）；
- X-Token 必须等于 D:\m\.env 的 MIA_HOST_RUNNER_KEY（secrets 比对，常数时间）；
- **短时票据（09-19 hy4 backlog①）**：静态钥匙只用于 POST /ticket 换票（内存态、默认 300s、单次使用），
  /exec 优先收 X-Ticket——泄露票据的窗口期= TTL，静态钥匙不再随每次执行过线；静态钥匙仍可直开 /exec（运维兜底，审计标注 auth=static）；
- **每次请求现读 settings.json 的 confirmLevel**——爸爸在设置页拨回非 full，秒级关门（fail-closed）；
- 全量审计：命令、退出码、时长 → mia_home/host_runner_audit.jsonl；
- 超时帽 600s、**超时=taskkill /F /T 全进程树击杀（09-19 hy4 backlog②）**、输出截断 200KB；
  命令经 ["bash","-lc",cmd] 参数列表执行（无 shell=True 拼接面）。
"""
import ctypes
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENV_FILE = Path(os.environ.get("MIA_HOST_RUNNER_ENV", r"D:\m\.env"))
# 09-18 hy4 复测补：MIA_HOST_RUNNER_SETTINGS 只许测试实例（非默认端口）用，生产口拒绝=堵"假档位文件"后门
_PORT = int(os.environ.get("MIA_HOST_RUNNER_PORT", "2026"))
_setenv = os.environ.get("MIA_HOST_RUNNER_SETTINGS", "")
if _setenv and _PORT == 2026 and os.environ.get("MIA_HOST_RUNNER_ALLOW_TEST_ENV") != "1":
    raise SystemExit("[拒绝] 生产端口 2026 不接受 MIA_HOST_RUNNER_SETTINGS 覆盖（堵假档位文件后门，hy4 复测①）")
SETTINGS = Path(_setenv or r"D:\m\workspace\settings.json")
AUDIT = Path(r"D:\m\guard\host_runner_audit.jsonl")  # 09-18 hy4 复测③：离开米娅可写的数据区（防删改审计）
BASH = r"C:\Git\bin\bash.exe"
MAX_TIMEOUT = 600
MAX_OUT = 200_000
def _env_key() -> str:
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"MIA_HOST_RUNNER_KEY=(.+)$", line.strip())
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return ""


def _stage() -> str:
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return str((s.get("general", {}) or {}).get("confirmLevel", "") or "")
    except Exception:
        return ""


def _audit(rec: dict) -> None:
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        if AUDIT.exists() and AUDIT.stat().st_size > 10_000_000:
            # r35（Qoder P2-26）：同仓 m_guard/office 账本都有轮转，宿主执行账本（命令全文）
            # 反而是三者中唯一无上限 append——磁盘写满会连带打断原子性
            p2 = Path(str(AUDIT) + ".2")
            if p2.exists():
                p2.unlink()
            p1 = Path(str(AUDIT) + ".1")
            if p1.exists():
                p1.rename(p2)
            AUDIT.rename(p1)
        with open(AUDIT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        # r35（Qoder P2-24）：最高权限路径的账本不许无声缺页——出声（fail-loud 同 core._token_audit）
        print(f"[host_runner] 审计写入失败（本条无痕！）: {type(e).__name__}: {e}", flush=True)


_FAILS = {}  # ip -> {"n","until"}（r35 Qoder P1-12：全局锁可被任意本机进程无限触发，改按来源分桶，同 m_guard._HITS 教训）
_SEM = __import__("threading").Semaphore(2)  # 并发闸：宿主 shell 同时最多 2 条（hy4 复测：无资源闸=句柄耗尽面）
_TICKET_TTL = int(os.environ.get("MIA_HOST_RUNNER_TICKET_TTL", "300"))
_TICKETS = {}  # sha256(ticket) -> 过期时刻（09-19 backlog①：内存态单次票据，重启即清零）
_TICKET_LOCK = __import__("threading").Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音默认 stderr 流水
        pass

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/exec", "/ticket"):
            self._send(404, {"error": "not found"})
            return
        key = _env_key()
        now = time.time()
        _ip = self.client_address[0]
        fl = _FAILS.setdefault(_ip, {"n": 0, "until": 0.0})
        if fl["until"] > now:
            _audit({"decision": "denied_rate", "ip": _ip})
            self._send(429, {"error": "鉴权失败过多，60 秒后再试"})
            return
        got_tok = str(self.headers.get("X-Token", "") or "")
        got_tkt = str(self.headers.get("X-Ticket", "") or "")
        auth = ""
        if key and got_tok and secrets.compare_digest(hashlib.sha256(got_tok.encode()).hexdigest(),
                                                      hashlib.sha256(key.encode()).hexdigest()):
            auth = "static"
        elif key and got_tkt:
            h = hashlib.sha256(got_tkt.encode()).hexdigest()
            with _TICKET_LOCK:
                exp = _TICKETS.pop(h, 0.0)  # 单次使用：验票即销，重放无效
            if exp and exp >= now:
                auth = "ticket"
        if not auth:
            # r35（Qoder P1-12）：只计"带了凭据而错"的爆破行为；空手路过者不占桶
            # （m_guard :310 同纪律"无/错=403 不占任何桶"）——堵任意本机进程 5 发瘫痪宿主执行
            if got_tok or got_tkt:
                fl["n"] += 1
                if fl["n"] >= 5:
                    fl["until"] = now + 60.0
                    fl["n"] = 0
            _audit({"decision": "denied_token", "ip": _ip})
            self._send(401, {"error": "bad token"})
            return
        fl["n"] = 0
        if self.path == "/ticket":
            # hy4 backlog①：发票口只认静态钥匙；票据=内存态、单次、默认 300s
            if auth != "static":
                _audit({"decision": "denied_ticket_mint", "auth": auth})
                self._send(401, {"error": "ticket 端点只收静态钥匙"})
                return
            t = secrets.token_urlsafe(32)
            with _TICKET_LOCK:
                for h in [h for h, exp in _TICKETS.items() if exp < now]:
                    _TICKETS.pop(h, None)  # 顺手清过期，防无界增长
                _TICKETS[hashlib.sha256(t.encode()).hexdigest()] = now + _TICKET_TTL
            _audit({"decision": "ticket_minted", "ttl": _TICKET_TTL})
            self._send(200, {"ticket": t, "ttl": _TICKET_TTL})
            return
        # r36k（09-28 爸令两轴正交）：旧的"仅 full 档放行"检查=后门时代遗产，撤——
        # 域由对话的工作区选（能到这里=爸爸在对话里选了宿主域，且 C1 档位门对 execute
        # 照常把关：strict/auto_edit 每次弹卡请示、plan 档根本到不了 execute）。
        # 档位与域不再互锁；审计照落（每次执行有 decision=ok 记录）。
        try:
            # R10.321 复测修（ds/glm 双评）：负 Content-Length 会 read(-1) 挂死线程、
            # 非 dict body 会让 req.get 抛未捕获异常——双双收紧
            n = max(0, min(int(self.headers.get("Content-Length", "0")), 65536))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(req, dict):
                raise ValueError("body must be a JSON object")
        except Exception:
            self._send(400, {"error": "bad json"})
            _audit({"decision": "error", "err": "bad body"})
            return
        cmd = str(req.get("cmd", "") or "")
        timeout = max(1, min(int(req.get("timeout") or 120), MAX_TIMEOUT))
        if not cmd.strip():
            self._send(400, {"error": "empty cmd"})
            return
        t0 = time.time()
        if not _SEM.acquire(blocking=False):
            self._send(429, {"error": "宿主执行并发已满（2），稍后再试"})
            _audit({"decision": "denied_concurrency"})
            return
        try:
            p = subprocess.Popen([BASH, "-lc", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace",
                                 cwd=os.environ.get("MIA_HOST_RUNNER_CWD", r"D:\m"))
            try:
                out_b, err_b = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                # hy4 backlog②：超时=全进程树击杀（run 只杀 bash 本体，孙进程会成孤儿继续跑）
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                try:
                    out_b, err_b = p.communicate(timeout=5)
                except Exception:
                    out_b, err_b = "", ""
                out = (out_b or "") + (("\n[stderr]\n" + err_b) if err_b else "")
                trunc = len(out) > MAX_OUT
                self._send(200, {"output": f"{out[:MAX_OUT]}\n[宿主执行超时 {timeout}s，进程树已全杀]",
                                 "exit_code": 124, "truncated": trunc})
                _audit({"decision": "timeout", "domain": "host-workspace", "auth": auth, "cmd": cmd, "secs": timeout})
                return
            out = (out_b or "") + (("\n[stderr]\n" + err_b) if err_b else "")
            trunc = len(out) > MAX_OUT
            self._send(200, {"output": out[:MAX_OUT], "exit_code": p.returncode, "truncated": trunc})
            _audit({"decision": "exec", "domain": "host-workspace", "auth": auth, "cmd": cmd,  # 全文不截断（hy4 复测③）
                    "exit_code": p.returncode, "secs": round(time.time() - t0, 2), "timeout": timeout})
        except Exception as e:
            self._send(200, {"output": f"[宿主执行异常: {str(e)[:200]}]", "exit_code": 1, "truncated": False})
            _audit({"decision": "error", "domain": "host-workspace", "auth": auth, "cmd": cmd, "err": str(e)[:200]})
        finally:
            _SEM.release()


if __name__ == "__main__":
    if not _env_key():
        raise SystemExit("MIA_HOST_RUNNER_KEY 不在 D:\\m\\.env——拒绝裸奔启动")
    if not os.path.exists(BASH):
        # r35（Qoder P2-25）：钥匙 fail-fast 了，同一条启动路径的硬依赖 shell 没校——
        # Git 不在位时服务"干净启动"然后每条 execute 都以"执行异常"失败，归因误导米娅
        raise SystemExit(f"[拒绝] 宿主 shell 不存在：{BASH}——完全访问档将无实义（装好 Git Bash 再启动）")
    print(f"[host_runner] listening 127.0.0.1:{_PORT} stage-file={SETTINGS} (r36k：域=对话工作区，档位不再互锁)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", _PORT), Handler).serve_forever()
