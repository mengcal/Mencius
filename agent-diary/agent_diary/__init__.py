# -*- coding: utf-8 -*-
"""
AgentDiary 📔

给智能体的工作日志系统——不是人类日记，是触发式记忆门禁

核心组件：
- DiaryStore: 存储层（情景日志/语义知识/程序手册）
- DiaryGate: 门禁中间件 v0.2（六条军规：硬拒/双钩/fail-closed/白名单/正向出口/审计）
- make_diary_tools: 创建read_diary/write_diary工具
- AuditDashboard: 审计仪表盘 v0.3
- run_mcp_server: 启动MCP Server v0.7（即插即用）
"""

from .store import DiaryStore
from .memory_gate import DiaryGate
from .tools import make_diary_tools
from .dashboard import AuditDashboard


def run_mcp_server():
    """启动MCP Server（v0.7新增）"""
    from .mcp_server import main
    main()


__version__ = "0.7.0"
__all__ = ["DiaryStore", "DiaryGate", "make_diary_tools", "AuditDashboard", "run_mcp_server"]
