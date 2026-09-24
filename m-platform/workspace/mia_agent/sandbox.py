# -*- coding: utf-8 -*-
"""mia_agent/sandbox.py —— execute 沙箱执行后端
拆分来源：D:\\m\\workspace\\agent_multimodel.py 原 L67-117（拆分方案 #2）。
（原 L67 的 `from deepagents import create_deep_agent, SubAgent` 不属本段实现，
 归 mia_agent/graph.py；SubAgent 在原文件中未被使用，拆分时已删。）
依赖：deepagents.backends（LocalShellBackend / ExecuteResponse）、os；httpx 方法内懒加载。
被引用：mia_agent/graph.py（create_deep_agent 的 backend，原 L1026；_compaction_middleware 的 backend，原 L951）。
"""
import os  # SandboxedShellBackend 用 os.environ 读 SANDBOX_TOKEN（原 L70）
from deepagents.backends import LocalShellBackend  # 原 L68
from deepagents.backends.protocol import ExecuteResponse as _ExecResp  # 原 L69

# R76 execute 沙箱化（爸爸定调"设置页 supreme/沙箱=容器时代之墙"）：
# 文件工具(ls/read/write/edit)已被 deepagents 锁在 root_dir=mia_home 内，唯独 execute 是无圈限裸 shell。
# 这里把 execute 经内网 POST 到 m-sandbox 容器的执行服务——沙箱只挂数据区，没有 settings.json/源码/档位，
# 米娅的 shell 物理上碰不到平台的"锁和脑"（对标 ZCode：执行面与守卫面分离）。
class SandboxedShellBackend(LocalShellBackend):  # 原 L76-117
    """execute → 沙箱执行服务（固定内网地址，带 X-Token）；其余继承本地实现（已锁 mia_home）。"""
    _URL = os.environ.get("SANDBOX_EXEC_URL") or "http://sandbox:9000/exec"  # compose 固定内网地址（管理员侧配置=env，不由任何输入拼装）

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._tok = os.environ.get("SANDBOX_TOKEN", "")

    @staticmethod
    def _payload(cmd: str, timeout: int) -> bytes:
        import json as _json
        return _json.dumps({"cmd": cmd, "timeout": timeout}).encode()

    def execute(self, cmd: str, *, timeout: int | None = None) -> _ExecResp:
        return self._call(cmd, timeout or 120)

    async def aexecute(self, cmd: str, *, timeout: int | None = None) -> _ExecResp:
        return await self._acall(cmd, timeout or 120)

    def _route(self):
        """09-17 深夜爸爸定纲"米娅=知夏同等权限"：confirmLevel=full 时 execute 落宿主
        runner（同款 Git Bash、同款机器权限）；其余档位走沙箱不变。每次现读配置——
        爸爸设置页拨回非 full，秒级关门（runner 侧还有第二道同款检查，双保险 fail-closed）。"""
        try:
            from settings_mgr import load_settings
            if str((load_settings().get("general", {}) or {}).get("confirmLevel", "")) == "full":
                return (os.environ.get("MIA_HOST_RUNNER_URL", "http://host.docker.internal:2026/exec"),
                        os.environ.get("MIA_HOST_RUNNER_KEY", ""))
        except Exception:
            pass
        return (self._URL, self._tok)

    # hy4 backlog①（09-19）：宿主 runner 走短时票据——静态钥匙只在 /ticket 换票时过线，
    # /exec 带 300s 单次票据；runner 重启会清票据（401 时换新票重试一次兜底）。
    _TICKET = {"v": "", "exp": 0.0}

    def _ticket(self, url: str, key: str) -> str:
        import time as _t
        now = _t.time()
        if self._TICKET["v"] and self._TICKET["exp"] > now + 30:
            return self._TICKET["v"]
        try:
            import httpx
            r = httpx.Client(timeout=15).post(url.replace("/exec", "/ticket"),
                                              headers={"X-Token": key})
            if r.status_code == 200:
                d = r.json()
                self._TICKET["v"] = str(d.get("ticket", "") or "")
                self._TICKET["exp"] = now + float(d.get("ttl", 300) or 300)
                return self._TICKET["v"]
        except Exception:
            pass
        return ""

    def _headers(self, url: str, tok: str) -> tuple[dict, bool]:
        """返回 (请求头, 是否用票据)。runner 路线优先票据，沙箱/兜底走静态 X-Token。"""
        if url.endswith("/exec") and tok:
            t = self._ticket(url, tok)
            if t:
                return {"Content-Type": "application/json", "X-Ticket": t}, True
        return {"Content-Type": "application/json", "X-Token": tok}, False

    def _call(self, cmd: str, timeout: int) -> _ExecResp:
        url, tok = self._route()
        try:
            import httpx
            headers, used_ticket = self._headers(url, tok)
            with httpx.Client(timeout=timeout + 15) as c:
                r = c.post(url, content=self._payload(cmd, timeout), headers=headers)
                if r.status_code == 401 and used_ticket:
                    self._TICKET["v"], self._TICKET["exp"] = "", 0.0  # runner 可能重启清了票，换新票重试一次
                    headers, used_ticket = self._headers(url, tok)
                    r = c.post(url, content=self._payload(cmd, timeout), headers=headers)
                if r.status_code != 200:
                    # 09-18 hy4 复测④：401/403/429 不许吞成空输出——米娅必须看见"门"的存在
                    return _ExecResp(output=f"[执行门拒绝 HTTP {r.status_code}: {r.text[:200]}]", exit_code=126, truncated=False)
                d = r.json()
        except Exception as e:
            return _ExecResp(output=f"[执行器不可达: {e}]", exit_code=1, truncated=False)
        return _ExecResp(output=str(d.get("output", "")), exit_code=int(d.get("exit_code", 1)),
                         truncated=bool(d.get("truncated", False)))

    async def _acall(self, cmd: str, timeout: int) -> _ExecResp:
        url, tok = self._route()
        try:
            import httpx
            headers, used_ticket = self._headers(url, tok)
            async with httpx.AsyncClient(timeout=timeout + 15) as c:
                r = await c.post(url, content=self._payload(cmd, timeout), headers=headers)
                if r.status_code == 401 and used_ticket:
                    self._TICKET["v"], self._TICKET["exp"] = "", 0.0
                    headers, used_ticket = self._headers(url, tok)
                    r = await c.post(url, content=self._payload(cmd, timeout), headers=headers)
                if r.status_code != 200:
                    return _ExecResp(output=f"[执行门拒绝 HTTP {r.status_code}: {r.text[:200]}]", exit_code=126, truncated=False)
                d = r.json()
        except Exception as e:
            return _ExecResp(output=f"[执行器不可达: {e}]", exit_code=1, truncated=False)
        return _ExecResp(output=str(d.get("output", "")), exit_code=int(d.get("exit_code", 1)),
                         truncated=bool(d.get("truncated", False)))
