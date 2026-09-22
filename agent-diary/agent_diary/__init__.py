# -*- coding: utf-8 -*-
"""
AgentDiary v1.3.2 📔

给智能体的工作日志系统——不是人类日记，是触发式记忆门禁

核心组件：
- DiaryStore: 存储层（情景日志/语义知识/程序手册）
- DiaryGate: 门禁中间件（六条军规：硬拒/双钩/fail-closed/白名单/正向出口/审计）
- DiaryHandoff: rolling 交接摘要（MVP·冷启动四行：在做/卡点/下一步/deadline）
- lint_diary: schema v1 §8 验收 lint（六项机械判据，验收官跑全单）
- make_diary_tools: 创建read_diary/write_diary工具
- AuditDashboard: 审计仪表盘
- VectorIndex: 向量语义搜索
- AutoConsolidator: 自动巩固+晋升流
- DiaryExporter/Importer: 导出导入
- LangGraphDiaryMiddleware: LangGraph宿主适配器
- ClaudePreToolUseHook: Claude宿主适配器（真实协议格式）
- DiaryMiddleware: 通用装饰器适配器
- run_mcp_server: 启动MCP Server

v1.3.0-mvp1（schema v1 RC2 对齐，MVP=V1 Alice 案：情景日志+rolling handoff）：
- ✅ 情景日志条目 frontmatter 结构化（id/author/kind/significance/private/source/confidence/refs/open_question）
- ✅ id 生成器（agent-YYYYMMDD-NNN，正则可判，撞号=0）
- ✅ handoff.md rolling 交接（各 agent 一份，冷启动四行模板）
- ✅ private 硬约束（结构化键+巩固/晋升/导出三关全跳+导出剔除 private 条目）
- ✅ 导入指令模式扫描（run_command/忽略指令/删除类，命中打 flag 进审计）
- ✅ lint 工具（§8 六项：字段完备/id唯一/canon纯净/private不出门/状态位不互噬/门禁双路）
- ✅ 审计 reason_code 稳定枚举 + JSONL 事件流（拦截/放行/晋升/导入）
- ✅ 门禁子串推断兜底记日志（§4）
"""

from .store import DiaryStore
from .memory_gate import DiaryGate
from .tools import make_diary_tools
from .dashboard import AuditDashboard
from .host_adapters import LangGraphDiaryMiddleware, ClaudePreToolUseHook, DiaryMiddleware
from .vector_index import VectorIndex
from .consolidator import AutoConsolidator
from .exchange import DiaryExporter, DiaryImporter
from .handoff import DiaryHandoff
from .lint import lint_diary


def run_mcp_server():
    """启动MCP Server"""
    from .mcp_server import main
    main()


__version__ = "1.3.2"
__all__ = [
    "DiaryStore", "DiaryGate", "make_diary_tools", "AuditDashboard",
    "LangGraphDiaryMiddleware", "ClaudePreToolUseHook", "DiaryMiddleware",
    "VectorIndex", "AutoConsolidator", "DiaryExporter", "DiaryImporter",
    "DiaryHandoff", "lint_diary",
    "run_mcp_server",
]
