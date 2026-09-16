# -*- coding: utf-8 -*-
"""
AgentDiary v1.1 📔

给智能体的工作日志系统——不是人类日记，是触发式记忆门禁

核心组件：
- DiaryStore: 存储层（情景日志/语义知识/程序手册）
- DiaryGate: 门禁中间件（六条军规：硬拒/双钩/fail-closed/白名单/正向出口/审计）
- make_diary_tools: 创建read_diary/write_diary工具
- AuditDashboard: 审计仪表盘
- VectorIndex: 向量语义搜索
- AutoConsolidator: 自动巩固+晋升流
- DiaryExporter/Importer: 导出导入
- LangGraphDiaryMiddleware: LangGraph宿主适配器
- ClaudePreToolUseHook: Claude宿主适配器（真实协议格式）
- DiaryMiddleware: 通用装饰器适配器
- run_mcp_server: 启动MCP Server（12个工具）

v1.1完整功能：
- ✅ 三层存储（情景/语义/程序）
- ✅ 门禁中间件（六条军规）
- ✅ MCP Server 12个工具
- ✅ 三个宿主适配器（LangGraph/Claude真实协议/通用）
- ✅ 审计仪表盘
- ✅ 向量语义搜索
- ✅ 自动巩固+晋升流（待审→晋升/拒绝）
- ✅ 导出导入（姐妹们互相分享）
"""

from .store import DiaryStore
from .memory_gate import DiaryGate
from .tools import make_diary_tools
from .dashboard import AuditDashboard
from .host_adapters import LangGraphDiaryMiddleware, ClaudePreToolUseHook, DiaryMiddleware
from .vector_index import VectorIndex
from .consolidator import AutoConsolidator
from .exchange import DiaryExporter, DiaryImporter


def run_mcp_server():
    """启动MCP Server"""
    from .mcp_server import main
    main()


__version__ = "1.1.0"
__all__ = [
    "DiaryStore", "DiaryGate", "make_diary_tools", "AuditDashboard",
    "LangGraphDiaryMiddleware", "ClaudePreToolUseHook", "DiaryMiddleware",
    "VectorIndex", "AutoConsolidator", "DiaryExporter", "DiaryImporter",
    "run_mcp_server",
]
