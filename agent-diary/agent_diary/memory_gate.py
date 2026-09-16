# -*- coding: utf-8 -*-
"""
AgentDiary — 门禁中间件 v0.2

六条军规（来自Mia C1/SubGate生产踩坑经验）：
1. 硬拒，不是提醒——工具根本不执行，不是"提醒一下"
2. 同步+异步双钩都要写——只写同步版上真服务必炸
3. fail-closed——门禁自己出错时默认拒，不是放
4. 拒信带正向出口——告诉模型"那该怎么办"，不然原地重试烧圈
5. 只读白名单——读笔记/写日志/纯查询先放行，不然死锁
6. 审计对账——拦截数=0本身就是告警，说明门禁没生效
"""

from typing import Any, Callable, Optional, Awaitable
from .store import DiaryStore


class DiaryGate:
    """
    记忆门禁——在工具调用层硬拦截

    用法（同步版）：
        gate = DiaryGate(store=store)

        # 包在工具调用外面
        def my_tool(request):
            allowed, reason = gate.wrap_tool_call_sync(session_id, tool_name, request)
            if not allowed:
                return reason  # 拒信，工具根本没执行
            return handler(request)

    用法（异步版）：
        async def my_tool_async(request):
            allowed, reason = await gate.wrap_tool_call_async(session_id, tool_name, request)
            if not allowed:
                return reason
            return await handler(request)
    """

    # 只读白名单——这些工具永远放行，不然死锁
    SAFE_LIST = {
        "read_diary", "write_diary", "search_diary",
        "list_files", "read_file", "search",
        "get_stats", "health_check",
    }

    def __init__(
        self,
        store: DiaryStore,
        execution_tools: list = None,
        read_before_execute: bool = True,
        write_after_task: bool = True,
        fail_closed: bool = True,
    ):
        self.store = store
        self.read_before_execute = read_before_execute
        self.write_after_task = write_after_task
        self.fail_closed = fail_closed  # 门禁出错时默认拒

        # 执行类工具列表（需要先读笔记才能调用）
        self.execution_tools = execution_tools or [
            "run_command", "execute_bash", "write_file", "edit_file",
            "send_email", "call_api", "deploy", "install",
            "delete_file", "move_file", "create_branch", "commit", "push",
        ]

        # 拦截计数（审计用）
        self._block_count = 0
        self._pass_count = 0

    def is_safe_tool(self, tool_name: str) -> bool:
        """判断是不是安全工具（白名单）"""
        return tool_name in self.SAFE_LIST

    def is_execution_tool(self, tool_name: str) -> bool:
        """判断是不是执行类工具"""
        if self.is_safe_tool(tool_name):
            return False
        return tool_name in self.execution_tools or any(
            exec_tool in tool_name.lower() for exec_tool in self.execution_tools
        )

    def _make_reject_message(self, tool_name: str, reason: str) -> str:
        """生成带正向出口的拒信"""
        return (
            f"⛔ 记忆门禁拦截：{reason}\n"
            f"工具：{tool_name}\n"
            f"请先调用 read_diary(关键词=本任务描述) 读取相关笔记，再重试本操作。"
        )

    def wrap_tool_call_sync(
        self,
        session_id: str,
        tool_name: str,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> tuple[bool, Any]:
        """
        同步版门禁——包在工具调用外面

        Returns:
            (allowed, result): 是否允许+结果（不允许时result是拒信）
        """
        try:
            # 白名单直接放行
            if self.is_safe_tool(tool_name):
                self._pass_count += 1
                return True, handler(request)

            # 非执行类工具放行
            if not self.is_execution_tool(tool_name):
                self._pass_count += 1
                return True, handler(request)

            # 前置门禁：检查有没有读笔记
            if self.read_before_execute:
                if not self.store.has_read_diary(session_id):
                    self._block_count += 1
                    self.store.log_block(session_id, tool_name, "read_not_done")
                    return False, self._make_reject_message(
                        tool_name, "调用执行类工具前必须先读笔记"
                    )

        except Exception as e:
            # 门禁自己的检查出错了
            if self.fail_closed:
                self._block_count += 1
                return False, f"⛔ 门禁异常（fail-closed）：{e}。请先调用 read_diary 确认上下文。"
            else:
                # fail-open：门禁检查出错了，放行但记一笔
                self._pass_count += 1
                # 注意：这里不能再调handler了！直接放行到handler
                # 调用方自己处理handler的执行
                pass

        # 执行工具（v0.6修复：handler的异常不被门禁catch，直接抛出）
        result = handler(request)
        self._pass_count += 1

        # 后置门禁：标记欠一条日志
        if self.write_after_task:
            self.store.mark_task_started(session_id)

        return True, result

    async def wrap_tool_call_async(
        self,
        session_id: str,
        tool_name: str,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> tuple[bool, Any]:
        """
        异步版门禁——和同步版逻辑一致，上真服务必须用这个
        """
        try:
            # 白名单直接放行
            if self.is_safe_tool(tool_name):
                self._pass_count += 1
                return True, await handler(request)

            # 非执行类工具放行
            if not self.is_execution_tool(tool_name):
                self._pass_count += 1
                return True, await handler(request)

            # 前置门禁：检查有没有读笔记
            if self.read_before_execute:
                if not self.store.has_read_diary(session_id):
                    self._block_count += 1
                    self.store.log_block(session_id, tool_name, "read_not_done")
                    return False, self._make_reject_message(
                        tool_name, "调用执行类工具前必须先读笔记"
                    )

        except Exception as e:
            # 门禁自己的检查出错了
            if self.fail_closed:
                self._block_count += 1
                return False, f"⛔ 门禁异常（fail-closed）：{e}。请先调用 read_diary 确认上下文。"
            else:
                # fail-open：门禁检查出错了，放行但记一笔
                self._pass_count += 1
                pass

        # 执行工具（v0.6修复：handler的异常不被门禁catch，直接抛出）
        result = await handler(request)
        self._pass_count += 1

        # 后置门禁：标记欠一条日志
        if self.write_after_task:
            self.store.mark_task_started(session_id)

        return True, result

    def check_task_completed(self, session_id: str) -> tuple[bool, str]:
        """
        后置门禁：检查任务完成时有没有写日志

        Returns:
            (allowed, reason): 是否允许+原因
        """
        if not self.write_after_task:
            return True, "门禁关闭"

        # 只读任务不算
        if not self.store.has_task_started(session_id):
            return True, "未启动任务，无需写日志"

        if self.store.has_written_diary(session_id):
            return True, "已写日志，放行"

        return False, (
            "任务完成后必须写工作日志（调用 write_diary）。"
            "写日志才算完成，不然不算完。"
        )

    # ── 审计 ──

    def get_stats(self) -> dict:
        """获取审计统计"""
        total = self._block_count + self._pass_count
        block_rate = self._block_count / total if total > 0 else 0
        return {
            "block_count": self._block_count,
            "pass_count": self._pass_count,
            "total": total,
            "block_rate": block_rate,
            # 拦截数=0本身就是告警——说明门禁没被路过或根本没生效
            "alert": self._block_count == 0 and total > 0,
        }
