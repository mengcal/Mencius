# -*- coding: utf-8 -*-
"""
AgentDiary v1.0 📔

给智能体的工作日志系统——不是人类日记，是触发式记忆门禁

核心组件：
- DiaryStore: 存储层（情景日志/语义知识/程序手册）
- DiaryGate: 门禁中间件（六条军规：硬拒/双钩/fail-closed/白名单/正向出口/审计）
- make_diary_tools: 创建read_diary/write_diary工具
- AuditDashboard: 审计仪表盘
- LangGraphDiaryMiddleware: LangGraph宿主适配器
- ClaudePreToolUseHook: Claude宿主适配器
- DiaryMiddleware: 通用装饰器适配器
- run_mcp_server: 启动MCP Server

v1.0正式发布：
- ✅ 三层存储（情景/语义/程序）
- ✅ 门禁中间件（六条军规）
- ✅ MCP Server（日记本+查询+gate_check）
- ✅ 三个宿主适配器（LangGraph/Claude/通用）
- ✅ 审计仪表盘
- ✅ 搜索升级（关键词权重+显著性加权）
"""

from .store import DiaryStore
from .memory_gate import DiaryGate
from .tools import make_diary_tools
from .dashboard import AuditDashboard
from .host_adapters import LangGraphDiaryMiddleware, ClaudePreToolUseHook, DiaryMiddleware


def run_mcp_server():
    """启动MCP Server"""
    from .mcp_server import main
    main()


__version__ = "1.0.0"
__all__ = [
    "DiaryStore", "DiaryGate", "make_diary_tools", "AuditDashboard",
    "LangGraphDiaryMiddleware", "ClaudePreToolUseHook", "DiaryMiddleware",
    "run_mcp_server",
]
