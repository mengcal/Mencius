# -*- coding: utf-8 -*-
"""
AgentDiary 宿主适配器 v0.9

真正的强制门禁在宿主家里！
MCP Server管存储和查询，宿主中间件管硬拦截。

现在做两个宿主适配器：
1. langgraph版：wrap_tool_call中间件
2. Claude系：pretool-use hook
"""

from typing import Any, Callable, Awaitable
from ..store import DiaryStore
from ..memory_gate import DiaryGate


# ═══════════════════════════════════════════════════════════
# 1. LangGraph 宿主适配器
# ═══════════════════════════════════════════════════════════

def create_langgraph_diary_middleware(
    store: DiaryStore,
    session_id: str,
    execution_tools: list = None,
):
    """
    创建LangGraph版的日记中间件

    用法：
        from agent_diary.host_adapters.langgraph import create_langgraph_diary_middleware

        middleware = create_langgraph_diary_middleware(
            store=store,
            session_id="user_123",
        )

        # 挂到你的agent上
        graph = builder.compile(
            middlewares=[middleware]
        )
    """
    gate = DiaryGate(store=store, execution_tools=execution_tools)

    async def wrap_tool_call(request, handler):
        """LangGraph中间件接口"""
        tool_name = request.tool_name if hasattr(request, 'tool_name') else str(request)

        allowed, result = await gate.wrap_tool_call_async(
            session_id=session_id,
            tool_name=tool_name,
            request=request,
            handler=handler,
        )

        if not allowed:
            # 拦截了，返回拒信
            return type('Result', (), {'content': str(result), 'is_error': True})()

        return result

    return wrap_tool_call


# ═══════════════════════════════════════════════════════════
# 2. Claude Desktop / Claude Code 宿主适配器
# ═══════════════════════════════════════════════════════════

def create_claude_pretool_use_hook(
    store: DiaryStore,
    session_id: str,
):
    """
    创建Claude系pretool-use hook

    用法：
        # 在claude_desktop_config.json里配置pretool-use hook
        # hook调用这个函数的检查逻辑

        hook = create_claude_pretool_use_hook(
            store=store,
            session_id="user_123",
        )

        # Claude会在调用工具前先调这个hook
        # hook返回拦截=不让调
    """
    gate = DiaryGate(store=store)

    def pretool_use_hook(tool_name: str, tool_input: dict) -> dict:
        """
        Claude pretool-use hook接口

        Returns:
            {"decision": "approve"} 放行
            {"decision": "block", "reason": "..."} 拦截
        """
        allowed, reason = gate.check_read_before(session_id, tool_name)

        if not allowed:
            return {
                "decision": "block",
                "reason": reason + "\n请先调用read_diary读取相关笔记，再重试。"
            }

        return {"decision": "approve"}

    return pretool_use_hook


# ═══════════════════════════════════════════════════════════
# 3. 通用中间件包装器（任何框架都能用）
# ═══════════════════════════════════════════════════════════

class DiaryMiddleware:
    """
    通用日记中间件——任何框架都能包

    用法：
        middleware = DiaryMiddleware(store=store, session_id="xxx")

        # 包在任何工具函数外面
        @middleware.wrap
        def my_execution_tool(arg1, arg2):
            # ... 干活
            pass
    """

    def __init__(self, store: DiaryStore, session_id: str):
        self.store = store
        self.session_id = session_id
        self.gate = DiaryGate(store=store)

    def wrap(self, func: Callable) -> Callable:
        """装饰器：包在工具函数外面"""

        def wrapper(*args, **kwargs):
            # 前置检查
            allowed, reason = self.gate.check_read_before(
                self.session_id,
                func.__name__,
            )
            if not allowed:
                return f"⛔ 门禁拦截：{reason}\n请先调用read_diary读取相关笔记。"

            # 执行原函数
            result = func(*args, **kwargs)

            # 后置标记
            self.store.mark_task_started(self.session_id)

            return result

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    async def awrap(self, func: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
        """异步装饰器"""

        async def wrapper(*args, **kwargs):
            allowed, reason = self.gate.check_read_before(
                self.session_id,
                func.__name__,
            )
            if not allowed:
                return f"⛔ 门禁拦截：{reason}\n请先调用read_diary读取相关笔记。"

            result = await func(*args, **kwargs)
            self.store.mark_task_started(self.session_id)
            return result

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
