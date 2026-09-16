# -*- coding: utf-8 -*-
"""
AgentDiary 宿主适配器 v0.9.1

修issue#3四条必改：
1. check_read_before方法——已补到DiaryGate里
2. LangGraph版——双钩中间件类（同步+异步）
3. Claude版——正确的hook接口
4. session_id——调用时传，不烤死在实例里
"""

from typing import Any, Callable, Awaitable
from ..store import DiaryStore
from ..memory_gate import DiaryGate


# ═══════════════════════════════════════════════════════════
# 1. LangGraph 宿主中间件（v0.9.1重写：双钩中间件类）
# ═══════════════════════════════════════════════════════════

class LangGraphDiaryMiddleware:
    """
    LangGraph版日记中间件（v0.9.1重写）

    用法：
        from agent_diary.host_adapters import LangGraphDiaryMiddleware

        middleware = LangGraphDiaryMiddleware(
            store=store,
            execution_tools=["run_command", "write_file"],
        )

        # 挂到graph上（LangGraph要的是中间件对象，不是裸函数）
        graph = builder.compile(
            middlewares=[middleware]
        )
    """

    def __init__(self, store: DiaryStore, execution_tools: list = None):
        self.store = store
        self.gate = DiaryGate(store=store, execution_tools=execution_tools)

    async def awrap_tool_call(self, request, handler):
        """异步版钩子（LangGraph用这个）"""
        tool_name = getattr(request, 'tool_name', str(request))

        # 从request里取session_id（不烤死在实例里！）
        session_id = getattr(request, 'session_id', 'default')

        allowed, result = await self.gate.wrap_tool_call_async(
            session_id=session_id,
            tool_name=tool_name,
            request=request,
            handler=handler,
        )

        if not allowed:
            return type('Result', (), {'content': str(result), 'is_error': True})()

        return result

    def wrap_tool_call(self, request, handler):
        """同步版钩子（双钩！军规2）"""
        tool_name = getattr(request, 'tool_name', str(request))
        session_id = getattr(request, 'session_id', 'default')

        allowed, result = self.gate.wrap_tool_call_sync(
            session_id=session_id,
            tool_name=tool_name,
            request=request,
            handler=handler,
        )

        if not allowed:
            return type('Result', (), {'content': str(result), 'is_error': True})()

        return result


# ═══════════════════════════════════════════════════════════
# 2. Claude Desktop pretool-use hook（v0.9.1重写：正确接口）
# ═══════════════════════════════════════════════════════════

class ClaudePreToolUseHook:
    """
    Claude Desktop pretool-use hook（v0.9.1重写）

    用法：
        hook = ClaudePreToolUseHook(store=store)

        # Claude Desktop配置pretool-use hook时调用这个函数
        result = hook(tool_name="Write", tool_input={"path": "xxx"}, session_id="user_123")
        # result = {"decision": "block", "reason": "..."} 拦截
        # result = {"decision": "approve"} 放行
    """

    def __init__(self, store: DiaryStore, execution_tools: list = None):
        self.store = store
        self.gate = DiaryGate(store=store, execution_tools=execution_tools)

    def __call__(self, tool_name: str, tool_input: dict, session_id: str = "default") -> dict:
        """
        pretool-use hook调用接口

        Args:
            tool_name: 工具名（Write/Read/Bash等）
            tool_input: 工具输入参数
            session_id: 当前会话ID（调用时传，不烤死）

        Returns:
            {"decision": "approve"} 放行
            {"decision": "block", "reason": "..."} 拦截
        """
        allowed, reason = self.gate.check_read_before(session_id, tool_name)

        if not allowed:
            return {
                "decision": "block",
                "reason": reason + "\n\n请先调用read_diary读取相关笔记，再重试本操作。"
            }

        return {"decision": "approve"}


# ═══════════════════════════════════════════════════════════
# 3. 通用装饰器版（任何框架都能用）
# ═══════════════════════════════════════════════════════════

class DiaryMiddleware:
    """
    通用日记中间件——任何框架都能包（v0.9.1修：session_id调用时传）

    用法：
        middleware = DiaryMiddleware(store=store)

        @middleware.wrap(session_id="user_123")
        def my_execution_tool(arg1, arg2):
            # ... 干活
            pass
    """

    def __init__(self, store: DiaryStore, execution_tools: list = None):
        self.store = store
        self.gate = DiaryGate(store=store, execution_tools=execution_tools)

    def wrap(self, session_id: str):
        """装饰器工厂：session_id在调用时传，不烤死在实例里"""

        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                allowed, reason = self.gate.check_read_before(
                    session_id,
                    func.__name__,
                )
                if not allowed:
                    return f"⛔ 门禁拦截：{reason}\n请先调用read_diary读取相关笔记。"

                result = func(*args, **kwargs)
                self.store.mark_task_started(session_id)
                return result

            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper

        return decorator

    def awrap(self, session_id: str):
        """异步装饰器工厂"""

        def decorator(func: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
            async def wrapper(*args, **kwargs):
                allowed, reason = self.gate.check_read_before(
                    session_id,
                    func.__name__,
                )
                if not allowed:
                    return f"⛔ 门禁拦截：{reason}\n请先调用read_diary读取相关笔记。"

                result = await func(*args, **kwargs)
                self.store.mark_task_started(session_id)
                return result

            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper

        return decorator


# ═══════════════════════════════════════════════════════════
# 冒烟测试（v0.9.1新增：每个适配器一个__main__冒烟）
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import shutil
    shutil.rmtree('/tmp/test_host_adapter', ignore_errors=True)

    store = DiaryStore('/tmp/test_host_adapter')

    print("=== 冒烟1：LangGraph中间件 ===")
    lg_mw = LangGraphDiaryMiddleware(store=store)
    print(f"  类创建OK: {type(lg_mw).__name__}")
    print(f"  有wrap_tool_call: {hasattr(lg_mw, 'wrap_tool_call')}")
    print(f"  有awrap_tool_call: {hasattr(lg_mw, 'awrap_tool_call')}")

    print()
    print("=== 冒烟2：Claude hook ===")
    claude_hook = ClaudePreToolUseHook(store=store)
    print(f"  类创建OK: {type(claude_hook).__name__}")
    result = claude_hook(tool_name="Write", tool_input={}, session_id="test_001")
    print(f"  调用OK: {result['decision']} (应该block，因为没读笔记)")

    print()
    print("=== 冒烟3：通用装饰器 ===")
    gen_mw = DiaryMiddleware(store=store)

    @gen_mw.wrap(session_id="test_002")
    def my_tool(arg):
        return f"执行: {arg}"

    print(f"  装饰器OK: {my_tool.__name__}")
    result = my_tool("hello")
    print(f"  调用结果: {str(result)[:50]}... (应该block)")

    print()
    print("✅ 三个适配器全部冒烟通过！")
