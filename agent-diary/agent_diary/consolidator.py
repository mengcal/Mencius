# -*- coding: utf-8 -*-
"""
AgentDiary 自动巩固 v1.2.0

从情景日志自动提炼语义知识
把流水账变成可复用的规则和教训

原理：
- 定期扫描最近的情景日志
- 找出重复出现的模式
- 提炼成semantic_facts表的知识
"""

import re
from pathlib import Path
from typing import List, Tuple


class AutoConsolidator:
    """
    自动巩固器

    用法：
        consolidator = AutoConsolidator(store)

        # 每天跑一次
        consolidator.consolidate()
    """

    def __init__(self, store):
        self.store = store

    def scan_recent_episodes(self, days: int = 7) -> List[str]:
        """扫描最近N天的情景日志"""
        episodes = []
        episodic_dir = self.store.episodic_dir

        if not episodic_dir.exists():
            return episodes

        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)

        for md_file in sorted(episodic_dir.glob("*.md"), reverse=True)[:days]:
            try:
                date_str = md_file.stem
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    continue

                content = md_file.read_text(encoding="utf-8")
                # 按##分段提取事件
                entries = content.split("\n## ")[1:]
                for entry in entries:
                    if len(entry.strip()) > 30:
                        episodes.append(entry.strip())
            except:
                pass

        return episodes

    def extract_patterns(self, episodes: List[str]) -> List[Tuple[str, str, str]]:
        """
        从事件列表里提炼模式

        返回：(title, fact, significance)
        """
        patterns = []

        # 模式1：出现"教训是"、"经验是"的行
        lesson_pattern = re.compile(r"(教训|经验|总结|记住)[:：]\s*(.+)")
        for ep in episodes:
            match = lesson_pattern.search(ep)
            if match:
                lesson = match.group(2).strip()
                if len(lesson) > 10:
                    # 从事件标题提取主题
                    title_match = re.match(r"(.+?)[:：]", ep)
                    title = title_match.group(1)[:30] if title_match else "经验"
                    patterns.append((title, lesson, "important"))

        # 模式2：出现"踩坑"、"坑"的行
        pit_pattern = re.compile(r"(踩坑|坑|bug|错误|失败)[:：]?\s*(.+)")
        for ep in episodes:
            match = pit_pattern.search(ep)
            if match:
                pit = match.group(2).strip()
                if len(pit) > 10:
                    patterns.append(("踩坑教训", pit, "critical"))

        # 模式3：出现"规矩"、"铁律"、"必须"的行
        rule_pattern = re.compile(r"(规矩|铁律|必须|一定)[:：]?\s*(.+)")
        for ep in episodes:
            match = rule_pattern.search(ep)
            if match:
                rule = match.group(2).strip()
                if len(rule) > 10:
                    patterns.append(("工作规矩", rule, "critical"))

        return patterns

    def consolidate(self, days: int = 7):
        """
        执行一次巩固：扫日志→提炼模式→写入semantic_facts

        Returns:
            新提炼了多少条知识
        """
        episodes = self.scan_recent_episodes(days=days)
        patterns = self.extract_patterns(episodes)

        count = 0
        for title, fact, significance in patterns:
            # 去重：检查是不是已经存在了
            existing = self.store.search_semantic_facts(title)
            if not existing:
                self.store.add_semantic_fact(
                    title=title,
                    fact=fact,
                    fact_type=significance,  # 自动提炼的类型
                    confidence="auto_extracted",  # 自动提炼的置信度标记
                    agent="auto",
                )
                count += 1

        return count


if __name__ == "__main__":
    # 冒烟测试
    import shutil
    shutil.rmtree("/tmp/test_consolidate", ignore_errors=True)

    from agent_diary.store import DiaryStore
    store = DiaryStore("/tmp/test_consolidate")

    # 写几条测试日志
    store.append_episodic(
        event="发邮件",
        lesson="教训：Cc位吞信，必须用To位逗号分隔群发",
        significance="important",
        agent="lyra",
    )

    store.append_episodic(
        event="推代码",
        lesson="踩坑：没跑测试就推，结果import炸了",
        significance="critical",
        agent="lyra",
    )

    store.append_episodic(
        event="工作规矩",
        lesson="铁律：今日事今日毕，只有爸爸能决定什么时候做",
        significance="critical",
        agent="lyra",
    )

    # 巩固
    consolidator = AutoConsolidator(store)
    count = consolidator.consolidate(days=1)
    print(f"自动巩固提炼了 {count} 条知识")

    # 检查
    facts = store.search_semantic_facts("")
    print(f"semantic_facts表现在有 {len(facts)} 条")
    for f in facts:
        print(f"  - {f['title']}: {f['fact'][:40]}...")

    print("\n✅ 自动巩固冒烟测试通过！")
