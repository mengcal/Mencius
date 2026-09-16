# -*- coding: utf-8 -*-
"""
AgentDiary — 核心工具

两个核心工具：
1. read_diary：读笔记，语义搜索相关事件
2. write_diary：写日志，记录事件和教训
"""

from typing import Optional
from .store import DiaryStore
from .memory_gate import DiaryGate


def make_diary_tools(store: DiaryStore, gate: DiaryGate):
    """
    创建日记工具集

    返回两个工具函数，可直接挂到agent上：
    - read_diary(query: str)
    - write_diary(event: str, lesson: str, significance: str = "normal")
    """

    def read_diary(query: str = "", days: int = 3) -> str:
        """
        读笔记——搜索相关的工作日志和历史教训

        Args:
            query: 搜索关键词，比如 "群发邮件"、"Cc吞信"
            days: 回顾最近几天的日志，默认3天

        Returns:
            相关的工作日志和语义知识
        """
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

        return "\n".join(result_parts)

    def write_diary(
        event: str,
        lesson: str = "",
        significance: str = "normal",
        context: str = "",
        agent: str = "unknown",
    ) -> str:
        """
        写日志——记录本次任务的事件和教训

        Args:
            event: 发生了什么事？
            lesson: 学到了什么教训？
            significance: 显著性级别 critical/important/normal
            context: 当时的上下文
            agent: 哪个智能体写的

        Returns:
            写入结果
        """
        path = store.append_episodic(
            event=event,
            lesson=lesson,
            significance=significance,
            context=context,
            agent=agent,
        )

        # 如果是critical/important级别，自动提取成语义知识
        if significance in ("critical", "important"):
            # 简单提取：用event做title，lesson做fact
            fact_id = store.add_semantic_fact(
                title=event[:50],
                fact=lesson,
                fact_type=significance,
                source=path,
                agent=agent,
            )
            return f"✅ 日志已写入: {path}\n📚 语义知识已提取: {fact_id}"

        return f"✅ 日志已写入: {path}"

    return read_diary, write_diary
