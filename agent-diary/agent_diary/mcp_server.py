# -*- coding: utf-8 -*-
"""
AgentDiary MCP Server v0.7

做成MCP Server，所有支持MCP的agent都能即插即用！
- Claude Desktop
- Cursor
- 各种支持MCP的IDE和agent框架

启动方式：
    python -m agent_diary.mcp_server
"""

from fastmcp import FastMCP
from .store import DiaryStore
from .memory_gate import DiaryGate
from .dashboard import AuditDashboard

# 创建MCP实例
mcp = FastMCP("agent-diary")

# 全局存储和门禁（启动时初始化）
store = None
gate = None
dashboard = None


def init_diary(base_dir: str = "./diary_data"):
    """初始化日记系统"""
    global store, gate, dashboard
    store = DiaryStore(base_dir)
    gate = DiaryGate(store=store)
    dashboard = AuditDashboard(store=store)


@mcp.tool()
def read_diary(query: str = "", days: int = 3, session_id: str = "default") -> str:
    """
    读笔记——搜索相关的工作日志和历史教训

    调用后自动标记 has_read_diary=1，门禁放行执行类工具。

    Args:
        query: 搜索关键词，比如 "群发邮件"、"Cc吞信"
        days: 回顾最近几天的日志，默认3天
        session_id: 当前会话ID，默认default

    Returns:
        相关的工作日志和语义知识
    """
    if store is None:
        init_diary()

    # 1. 读最近N天的情景日志
    episodic = store.read_recent_episodic(days=days)

    # 2. 语义搜索相关知识
    semantic_results = store.search_semantic_facts(query) if query else []

    result_parts = []
    result_parts.append("📔 【最近工作日志】")
    result_parts.append(episodic)

    if semantic_results:
        result_parts.append("\n📚 【相关知识】")
        for fact in semantic_results:
            result_parts.append(f"- **{fact['title']}**: {fact['fact']} (置信度: {fact['confidence']})")

    # 自动打标记
    store.mark_read_diary(session_id)

    return "\n".join(result_parts)


@mcp.tool()
def write_diary(
    event: str,
    lesson: str = "",
    significance: str = "normal",
    context: str = "",
    agent: str = "unknown",
    session_id: str = "default",
) -> str:
    """
    写日志——记录本次任务的事件和教训

    任务完成必须调这个！不然门禁判"未完成"。

    Args:
        event: 发生了什么事？
        lesson: 学到了什么教训？
        significance: 显著性级别 critical/important/normal
        context: 当时的上下文
        agent: 哪个智能体写的
        session_id: 当前会话ID

    Returns:
        写入结果
    """
    if store is None:
        init_diary()

    path = store.append_episodic(
        event=event,
        lesson=lesson,
        significance=significance,
        context=context,
        agent=agent,
    )

    # 如果是critical/important级别，自动提取成语义知识
    fact_id = None
    if significance in ("critical", "important"):
        fact_id = store.add_semantic_fact(
            title=event[:50],
            fact=lesson,
            fact_type=significance,
            source=path,
            agent=agent,
        )

    # 自动打标记
    store.mark_written_diary(session_id)

    result = f"✅ 日志已写入: {path}"
    if fact_id:
        result += f"\n📚 语义知识已提取: {fact_id}"

    return result


@mcp.tool()
def diary_dashboard() -> str:
    """
    审计仪表盘——看门禁工作得好不好

    返回今天的：
    - 总任务数
    - 读笔记率
    - 写日志率
    - 门禁拦截次数
    - 告警（拦截数=0说明门禁没生效）
    """
    if dashboard is None:
        init_diary()

    return dashboard.report()


@mcp.tool()
def diary_stats() -> dict:
    """
    机器可读的统计摘要

    返回JSON格式：
    - total_today: 今天总任务数
    - read_today: 读了笔记的
    - write_today: 写了日志的
    - block_today: 拦截次数
    - alert: 有没有告警
    """
    if dashboard is None:
        init_diary()

    return dashboard.summary()


@mcp.resource("diary://today")
def today_diary() -> str:
    """今天的工作日志"""
    if store is None:
        init_diary()
    return store.read_recent_episodic(days=1)


@mcp.prompt()
def diary_gate_rules() -> str:
    """
    给agent的提示词——告诉agent怎么用日记系统
    """
    return """
    你有一个工作日志系统（AgentDiary），必须遵守以下规则：

    1. **动手前必读笔记**：调用任何执行类工具（写文件、跑命令、发邮件）前，必须先调用 read_diary 读取相关笔记
    2. **完成后必写日志**：任务完成后，必须调用 write_diary 记录事件和教训

    不读笔记就动手 = 被门禁拦住
    不写日志就收工 = 任务不算完成

    显著性级别：
    - critical：爸爸铁律、关键决策、大坑
    - important：小坑、小决策
    - normal：普通记录
    """


def main():
    """启动MCP Server"""
    init_diary()
    mcp.run()


if __name__ == "__main__":
    main()
