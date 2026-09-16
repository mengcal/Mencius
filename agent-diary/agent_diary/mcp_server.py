# -*- coding: utf-8 -*-
"""
AgentDiary MCP Server v0.8

诚实定位（celia issue #2修正）：
- MCP面 = 存储/检索/审计 + 门禁状态查询
- 强制面 = 宿主中间件（DiaryGate类已具备，就差宿主接线）

注意：MCP server天然拦不住宿主那边的执行类工具！
真正的强制门禁要在宿主家里装中间件（Claude pretool-use hook / langgraph wrap_tool_call）。
这个MCP Server提供的是：日记本 + 门禁状态查询，不是强制性拦截！

启动方式：
    AGENT_DIARY_HOME=/path/to/diary python -m agent_diary.mcp_server
"""

import os
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


def init_diary():
    """
    初始化日记系统（v0.8修正：base_dir必须显式配置，不然拒绝启动）

    环境变量：AGENT_DIARY_HOME
    未配置就启动 = fail-closed 拒绝启动
    """
    global store, gate, dashboard

    # v0.8必改：base_dir必须显式配置，不能用相对路径默认值
    base_dir = os.environ.get("AGENT_DIARY_HOME")
    if not base_dir:
        raise RuntimeError(
            "AGENT_DIARY_HOME 环境变量未设置！\n"
            "MCP Server由客户端拉起，CWD不受我们控制。\n"
            "必须显式配置日记存储路径，不然下次启动就失忆了。\n"
            "请在MCP配置里设置环境变量 AGENT_DIARY_HOME=/abs/path/to/diary"
        )

    store = DiaryStore(base_dir)
    gate = DiaryGate(store=store)
    dashboard = AuditDashboard(store=store)


@mcp.tool()
def read_diary(
    query: str = "",
    days: int = 3,
    session_id: str = "",  # v0.8必改：必填，不给默认值
) -> str:
    """
    读笔记——搜索相关的工作日志和历史教训

    调用后自动标记 has_read_diary=1。

    Args:
        query: 搜索关键词，比如 "群发邮件"、"Cc吞信"
        days: 回顾最近几天的日志，默认3天
        session_id: 【必填】当前会话ID，每个会话唯一

    Returns:
        相关的工作日志和语义知识
    """
    if not session_id:
        return "❌ 错误：session_id 是必填参数！每个会话必须有唯一ID，不然所有客户端共用一个状态，A读了笔记B的工具也算已读。"

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
    session_id: str = "",  # v0.8必改：必填，不给默认值
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
        session_id: 【必填】当前会话ID

    Returns:
        写入结果
    """
    if not session_id:
        return "❌ 错误：session_id 是必填参数！每个会话必须有唯一ID。"

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
def gate_check(session_id: str = "") -> str:
    """
    【v0.8新增】门禁状态查询——宿主收工前必查！

    这是MCP模式下的门禁替代方案：
    - MCP server天然拦不住宿主那边的工具执行
    - 但宿主可以在收工前调这个工具，问一声"能不能收工"
    - 把check_task_completed的判定权经MCP交出来

    Args:
        session_id: 【必填】当前会话ID

    Returns:
        能不能收工，为什么
    """
    if not session_id:
        return "❌ 错误：session_id 是必填参数！"

    if store is None:
        init_diary()

    allowed, reason = gate.check_task_completed(session_id)

    if allowed:
        return f"✅ 可以收工：{reason}"
    else:
        return f"⛔ 不能收工：{reason}\n\n请先调 write_diary 把本次任务的事件和教训记下来。"


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


@mcp.tool()
def semantic_search(query: str, top_k: int = 5) -> str:
    """
    v1.3.0: 向量语义搜索——理解意思，不是字面匹配

    用法：
        semantic_search("怎么给大家发邮件不丢信")
        → 第一个结果就是"Cc吞信"

    Args:
        query: 自然语言搜索词
        top_k: 返回前几条

    Returns:
        语义最相关的几条记录
    """
    if store is None:
        init_diary()

    try:
        from .vector_index import VectorIndex
        vi = VectorIndex(store)
        vi.build_index()
        results = vi.search(query, top_k=top_k)

        output = [f"🔍 语义搜索结果（'{query}'）："]
        for i, r in enumerate(results, 1):
            output.append(f"{i}. [{r['score']:.2f}] {r['text'][:80]}...")

        return "\n".join(output)
    except Exception as e:
        return f"❌ 向量搜索失败: {e}（可能没装sentence-transformers）"


@mcp.tool()
def consolidate(days: int = 7) -> str:
    """
    v1.3.0: 自动巩固——从情景日志自动提炼语义知识

    定期跑，把流水账变成可复用的规则和教训！

    Args:
        days: 回顾最近几天的日志，默认7天

    Returns:
        提炼了多少条新知识
    """
    if store is None:
        init_diary()

    try:
        from .consolidator import AutoConsolidator
        consolidator = AutoConsolidator(store)
        count = consolidator.consolidate(days=days)

        return f"✅ 自动巩固完成！从最近{days}天的日志里提炼了 {count} 条新知识"
    except Exception as e:
        return f"❌ 自动巩固失败: {e}"


@mcp.tool()
def list_pending_facts() -> str:
    """
    v1.3.0: 列出所有待审的自动提炼知识

    看看哪些知识是自动提炼的，需要人工确认。

    Returns:
        待审知识列表
    """
    if store is None:
        init_diary()

    try:
        from .consolidator import AutoConsolidator
        consolidator = AutoConsolidator(store)
        pending = consolidator.list_pending()

        if not pending:
            return "✅ 没有待审知识，全部已确认！"

        output = [f"📋 待审知识列表（共 {len(pending)} 条）："]
        for p in pending:
            output.append(f"- [{p['id']}] {p['title']}: {p['fact'][:60]}...")

        return "\n".join(output)
    except Exception as e:
        return f"❌ 查询失败: {e}"


@mcp.tool()
def promote_fact(fact_id: str) -> str:
    """
    v1.3.0: 晋升一条待审知识为正式知识

    Args:
        fact_id: 知识ID（从list_pending_facts获取）

    Returns:
        晋升结果
    """
    if store is None:
        init_diary()

    try:
        from .consolidator import AutoConsolidator
        consolidator = AutoConsolidator(store)
        return consolidator.promote(fact_id)
    except Exception as e:
        return f"❌ 晋升失败: {e}"


@mcp.tool()
def reject_fact(fact_id: str) -> str:
    """
    v1.3.0: 拒绝一条待审知识（删除）

    Args:
        fact_id: 知识ID（从list_pending_facts获取）

    Returns:
        删除结果
    """
    if store is None:
        init_diary()

    try:
        from .consolidator import AutoConsolidator
        consolidator = AutoConsolidator(store)
        return consolidator.reject(fact_id)
    except Exception as e:
        return f"❌ 删除失败: {e}"


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

    v0.8诚实修正：
    MCP模式下没有强制性拦截！
    真正的门禁要在宿主家里装中间件。
    这里是建议性的规则，不是硬门禁。
    """
    return """
    你有一个工作日志系统（AgentDiary），建议遵守以下规则：

    1. **动手前读笔记**：调用执行类工具前，最好先调用 read_diary 读取相关笔记
    2. **完成后写日志**：任务完成后，最好调用 write_diary 记录事件和教训

    注意：这是建议性规则，不是强制门禁！
    真正的强制门禁需要在宿主家里装中间件（DiaryGate类）。
    收工前建议调 gate_check 问一声能不能收工。

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
