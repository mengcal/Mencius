"""R76 沙箱执行服务：跑在 m-sandbox 容器内（只挂数据区 /data/mia_home）。
workplatform 的 execute 经宿主回环 POST 到这里执行——沙箱容器里【没有】settings.json/源码/档位文件，
所以助手的 shell 物理上碰不到平台的"锁和脑"（参考成熟 agent 平台：执行面与守卫面分离）。
端口经宿主回环发布 127.0.0.1:9090；请求头 X-Token 须等于宿主 .env 的 SANDBOX_TOKEN。

R10.5（评审C 战场移交：宿主侧 runner 频控+审计）：
- 频控：全局滑动窗口 60s ≤120 次（助手正常干活远低于此；本机任意进程可打 9090，
  窗口防"无限并发压死 runner"）；窗口内存态，重启清零=可接受（runner 无持久义务）。
- 审计：每次 /exec 落一行到容器本地 /var/log/runner_audit.jsonl（时间/来源IP/命令头/退出码）。
  容器本地文件助手摸不到（她只有 /data 卷的写权）；她能自残 runner 但删不到 docker logs——
  双通道出声：审计行同时 print 到 stdout（宿主 docker logs 可查）。
  已知边界（诚实清单）：沙箱内 root 理论上可自残 runner 进程本身（非提权，老账维持）。
"""
import hmac
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("SANDBOX_TOKEN", "")
DATA_DIR = os.environ.get("SANDBOX_DATA_DIR", "/data/mia_home")
MAX_OUT = 100_000
MAX_TIMEOUT = 600  # R79⑨：单命令上限 10 分钟（客户端传大值也不能把 runner 线程占死）
AUDIT_LOG = os.environ.get("RUNNER_AUDIT_LOG", "/var/log/runner_audit.jsonl")

_HITS: list = []          # R10.5：全局滑动窗口（60s ≤120）
_RATE_WINDOW = 60.0
_RATE_MAX = 120
_AUDIT_LOCK = threading.Lock()  # ThreadingHTTPServer 多线程：窗口与账本都要锁


def _rate_ok() -> bool:
    now = time.time()
    with _AUDIT_LOCK:
        while _HITS and now - _HITS[0] > _RATE_WINDOW:
            _HITS.pop(0)
        if len(_HITS) >= _RATE_MAX:
            return False
        _HITS.append(now)
    return True


def _audit(action: str, **extra) -> None:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action}
    rec.update({k: str(v)[:200] for k, v in extra.items()})
    line = json.dumps(rec, ensure_ascii=False)
    print(f"[runner-audit] {line}", flush=True)  # 宿主 docker logs 通道（助手删不到）
    try:
        with _AUDIT_LOCK:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass  # 容器本地文件不可写时只留 stdout 通道


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音默认访问日志（审计走 _audit）
        pass

    def _authed(self) -> bool:
        # R79⑨：常数时间比较防时序侧信道；encode 规避 compare_digest 对非 ASCII str 抛 TypeError
        return bool(TOKEN) and hmac.compare_digest(
            TOKEN.encode(), str(self.headers.get("X-Token", "")).encode())

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            self._send(400, {"error": "bad json"})
            return
        if self.path != "/exec":
            self._send(404, {"error": "not found"})
            return
        client_ip = self.client_address[0] if self.client_address else "?"
        if not self._authed():
            _audit("auth_denied", ip=client_ip)
            self._send(401, {"error": "bad token"})
            return
        if not _rate_ok():
            _audit("rate_limited", ip=client_ip)
            self._send(429, {"error": "rate limited (120/min)"})
            return
        cmd = str(req.get("command") or req.get("cmd") or "").strip()
        if not cmd:
            self._send(400, {"error": "empty command"})
            return
        try:  # R79⑨：timeout 夹到 [1, 600]（客户端乱传负数/巨大值/非数字都不炸 runner）
            timeout = max(1, min(int(req.get("timeout") or 120), MAX_TIMEOUT))
        except (TypeError, ValueError):
            timeout = 120
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            p = subprocess.run(
                ["sh", "-c", cmd],
                cwd=DATA_DIR, capture_output=True, text=True,
                timeout=timeout,
            )
            out = (p.stdout or "") + (p.stderr or "")
            truncated = len(out) > MAX_OUT
            _audit("exec", ip=client_ip, cmd=cmd, exit=p.returncode, truncated=truncated)
            self._send(200, {"output": out[:MAX_OUT], "exit_code": p.returncode, "truncated": truncated})
        except subprocess.TimeoutExpired:
            _audit("exec_timeout", ip=client_ip, cmd=cmd, timeout=timeout)
            self._send(200, {"output": f"[timeout after {timeout}s]", "exit_code": 124, "truncated": False})
        except Exception as e:
            _audit("exec_error", ip=client_ip, cmd=cmd, err=type(e).__name__)
            self._send(500, {"error": str(e)})

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    _audit("runner_start", data_dir=DATA_DIR)
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
