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

# R76 execute 沙箱化（管理员定调"设置页 supreme/沙箱=容器时代之墙"）：
# 文件工具(ls/read/write/edit)已被 deepagents 锁在 root_dir=mia_home 内，唯独 execute 是无圈限裸 shell。
# 这里把 execute 经内网 POST 到 m-sandbox 容器的执行服务——沙箱只挂数据区，没有 settings.json/源码/档位，
# 助手的 shell 物理上碰不到平台的"锁和脑"（参考成熟 agent 平台：执行面与守卫面分离）。
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

    def _call(self, cmd: str, timeout: int) -> _ExecResp:
        try:
            import httpx
            with httpx.Client(timeout=timeout + 15) as c:
                r = c.post(self._URL, content=self._payload(cmd, timeout),
                           headers={"Content-Type": "application/json", "X-Token": self._tok})
                d = r.json()
        except Exception as e:
            return _ExecResp(output=f"[沙箱执行器不可达: {e}]", exit_code=1, truncated=False)
        return _ExecResp(output=str(d.get("output", "")), exit_code=int(d.get("exit_code", 1)),
                         truncated=bool(d.get("truncated", False)))

    async def _acall(self, cmd: str, timeout: int) -> _ExecResp:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout + 15) as c:
                r = await c.post(self._URL, content=self._payload(cmd, timeout),
                                 headers={"Content-Type": "application/json", "X-Token": self._tok})
                d = r.json()
        except Exception as e:
            return _ExecResp(output=f"[沙箱执行器不可达: {e}]", exit_code=1, truncated=False)
        return _ExecResp(output=str(d.get("output", "")), exit_code=int(d.get("exit_code", 1)),
                         truncated=bool(d.get("truncated", False)))
