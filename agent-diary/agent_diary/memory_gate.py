# -*- coding: utf-8 -*-
"""
AgentDiary — 门禁中间件

核心功能：
1. 前置门禁：调用执行类工具前，检查有没有读过笔记
2. 后置门禁：任务结束时，检查有没有写过日志

不是建议，是门禁——不读笔记就不让调工具，不写日志就不算完成。
"""

from typing import Any, Callable, Optional
from .store import DiaryStore


class MemoryGate:
    """
    记忆门禁——在工具调用层硬拦截

    用法：
        gate = MemoryGate(store=store)

        # 前置检查：调用执行类工具前
        allowed, reason = gate.check_read_before(session_id, tool_name)
        if not allowed:
            return f"⛔ 门禁拦截：{reason}。请先调用 read_diary 读取相关笔记。"

        # 后置检查：任务完成后
        gate.mark_task_started(session_id)
        # ... 执行任务 ...
        gate.mark_task_completed(session_id)
    """

    def __init__(
        self,
        store: DiaryStore,
        execution_tools: list = None,
        read_before_execute: bool = True,
        write_after_task: bool = True,
    ):
        self.store = store
        self.read_before_execute = read_before_execute
        self.write_after_task = write_after_task

        # 执行类工具列表（需要先读笔记才能调用）
        self.execution_tools = execution_tools or [
            "run_command", "execute_bash", "write_file", "edit_file",
            "send_email", "call_api", "deploy", "install",
        ]

    def is_execution_tool(self, tool_name: str) -> bool:
        """判断是不是执行类工具"""
        return tool_name in self.execution_tools or any(
            exec_tool in tool_name.lower() for exec_tool in self.execution_tools
        )

    def check_read_before(self, session_id: str, tool_name: str) -> tuple[bool, str]:
        """
        前置门禁：检查是否读了笔记

        Returns:
            (allowed, reason): 是否允许+原因
        """
        if not self.read_before_execute:
            return True, "门禁关闭"

        if not self.is_execution_tool(tool_name):
            return True, "非执行类工具，放行"

        if self.store.has_read_diary(session_id):
            return True, "已读笔记，放行"

        return False, f"调用执行类工具 '{tool_name}' 前必须先读笔记"

    def check_write_after(self, session_id: str) -> tuple[bool, str]:
        """
        后置门禁：检查是否写了日志

        Returns:
            (allowed, reason): 是否允许+原因
        """
        if not self.write_after_task:
            return True, "门禁关闭"

        if self.store.has_written_diary(session_id):
            return True, "已写日志，放行"

        return False, "任务完成后必须写工作日志（调用 write_diary）"

    def mark_task_started(self, session_id: str):
        """标记任务开始"""
        self.store.mark_read_diary(session_id)

    def mark_task_completed(self, session_id: str):
        """标记任务完成（检查有没有写日志）"""
        allowed, reason = self.check_write_after(session_id)
        if not allowed:
            return False, reason
        return True, "任务完成，日志已记录"

    # ── 审计 ──

    def get_stats(self) -> dict:
        """获取审计统计"""
        return self.store.get_audit_stats()
