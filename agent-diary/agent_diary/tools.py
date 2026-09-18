# -*- coding: utf-8 -*-
"""
AgentDiary — 核心工具

两个核心工具：
1. read_diary：读笔记，语义搜索相关事件
2. write_diary：写日志，记录事件和教训

§2 author 盖章：server 端派生优先（环境变量 AGENT_DIARY_AUTHOR），客户端自报降权。
"""

import os
from typing import Optional, List
from .store import DiaryStore
from .memory_gate import DiaryGate


def _resolve_author(client_agent: str) -> str:
    """§2 author 盖章：AGENT_DIARY_AUTHOR 派生优先，客户端自报降权"""
    return os.environ.get("AGENT_DIARY_AUTHOR", "").strip() or client_agent or "unknown"


def make_diary_tools(store: DiaryStore, gate: DiaryGate, session_id: str = "default"):
    """
    创建日记工具集

    返回两个工具函数，可直接挂到agent上：
    - read_diary(query: str)
    - write_diary(event: str, lesson: str, significance: str = "normal")

    Args:
        store: 存储层
        gate: 门禁中间件
        session_id: 当前会话ID（v0.6修复：自动打标记用）
    """

    # v1.1.0: 向量索引（懒加载）
    _vector_index = None

    def _get_vector_index():
        nonlocal _vector_index
        if _vector_index is None:
            try:
                from .vector_index import VectorIndex
                _vector_index = VectorIndex(store)
                _vector_index.build_index()
            except Exception as e:
                print(f"向量索引加载失败，降级为关键词搜索: {e}")
                return None
        return _vector_index

    def read_diary(query: str = "", days: int = 3, semantic: bool = False) -> str:
        """
        读笔记——搜索相关的工作日志和历史教训

        调用后自动标记 has_read_diary=1（v0.6修复）

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

        # v1.1.0: 向量语义搜索
        vector_results = []
        if query and semantic:
            vi = _get_vector_index()
            if vi:
                vector_results = vi.search(query, top_k=3)

        result_parts = []
        result_parts.append("📔 【最近工作日志】")
        result_parts.append(episodic)

        if semantic_results:
            result_parts.append("\n📚 【相关知识】")
            for fact in semantic_results:
                result_parts.append(f"- **{fact['title']}**: {fact['fact']} (置信度: {fact['confidence']})")

        if vector_results:
            result_parts.append("\n🧠 【语义搜索结果】")
            for r in vector_results:
                result_parts.append(f"- [{r['score']:.2f}] {r['text'][:80]}...")

        # v0.6修复：读了笔记，自动打标记
        store.mark_read_diary(session_id)

        return "\n".join(result_parts)

    def write_diary(
        event: str,
        lesson: str = "",
        significance: str = "normal",
        context: str = "",
        agent: str = "unknown",
        kind: str = "lesson",
        private: bool = False,
        refs: Optional[List[str]] = None,
        open_question: str = "",
        source_origin: str = "",
    ) -> str:
        """
        写日志——记录本次任务的事件和教训（schema v1 §2 frontmatter）

        调用后自动标记 has_written_diary=1（v0.6修复）

        Args:
            event: 发生了什么事？
            lesson: 学到了什么教训/为什么（理由原文保留）
            significance: 显著性级别 critical/important/normal
            context: 当时的上下文
            agent: 哪个智能体写的（§2：AGENT_DIARY_AUTHOR 派生优先，自报降权）
            kind: lesson|decision|pitfall|rule|promise|question
            private: true=永不进共享层/导出/巩固（三关全跳）
            refs: 关联条目 id 列表
            open_question: 悬念字段（可选，V4 决议）
            source_origin: 来源原文（默认空=本次会话直接产生）

        Returns:
            写入结果
        """
        author = _resolve_author(agent)
        path = store.append_episodic(
            event=event,
            lesson=lesson,
            significance=significance,
            context=context,
            agent=author,
            kind=kind,
            private=private,
            refs=refs,
            open_question=open_question,
            source_channel="session",
            source_origin=source_origin,
        )

        # 如果是critical/important级别，自动提取成语义知识
        if significance in ("critical", "important"):
            # 简单提取：用event做title，lesson做fact（private 同步隔离）
            fact_id = store.add_semantic_fact(
                title=event[:50],
                fact=lesson,
                fact_type=significance,
                source=path,
                agent=author,
                private=private,
            )
            result = f"✅ 日志已写入: {path}\n📚 语义知识已提取: {fact_id}"
        else:
            result = f"✅ 日志已写入: {path}"

        # v0.6修复：写了日志，自动打标记
        store.mark_written_diary(session_id)

        return result

    return read_diary, write_diary
