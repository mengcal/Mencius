# -*- coding: utf-8 -*-
"""
AgentDiary — 存储层

三层记忆：
1. 情景日志（Episodic Log）：按时间记录的原始事件流，Markdown文件
2. 语义知识（Semantic Facts）：从事件中抽象的规则/事实，SQLite
3. 程序手册（Procedural Skills）：可复用工作流，Markdown
"""

import os
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


class DiaryStore:
    """工作日志存储层"""

    def __init__(self, base_dir: str = "./diary_data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.episodic_dir = self.base_dir / "episodic"
        self.semantic_dir = self.base_dir / "semantic"
        self.procedural_dir = self.base_dir / "procedural"

        for d in [self.episodic_dir, self.semantic_dir, self.procedural_dir]:
            d.mkdir(exist_ok=True)

        # SQLite for semantic facts
        self.db_path = self.base_dir / "agent_diary.db"
        self._init_db()

    def _init_db(self):
        """初始化SQLite表"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 语义知识表
        c.execute("""
            CREATE TABLE IF NOT EXISTS semantic_facts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                fact TEXT NOT NULL,
                type TEXT NOT NULL,
                source TEXT,
                agent TEXT,
                date TEXT,
                confidence TEXT DEFAULT 'verified',
                tags TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # 会话记录（跟踪是否读了/写了）
        c.execute("""
            CREATE TABLE IF NOT EXISTS session_log (
                session_id TEXT PRIMARY KEY,
                has_read_diary INTEGER DEFAULT 0,
                has_written_diary INTEGER DEFAULT 0,
                task_started INTEGER DEFAULT 0,
                task_started_at TEXT,
                task_completed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # 拦截记录（审计用）
        c.execute("""
            CREATE TABLE IF NOT EXISTS block_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                tool_name TEXT,
                reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
        conn.close()

    # ── 情景日志（Markdown） ──

    def get_episodic_path(self, date: Optional[str] = None) -> Path:
        """获取某天的情景日志文件路径"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.episodic_dir / f"{date}.md"

    def append_episodic(self, event: str, lesson: str, significance: str = "normal",
                        agent: str = "unknown", context: str = "") -> str:
        """追加一条情景日志"""
        path = self.get_episodic_path()
        now = datetime.now().strftime("%H:%M")

        # 显著性emoji
        emoji_map = {"critical": "🔴", "important": "🟡", "normal": "⚪"}
        emoji = emoji_map.get(significance, "⚪")

        entry = f"""
## {now} {emoji} [{significance}] {agent}

**事件**: {event}

**上下文**: {context if context else '-'}

**教训/结果**: {lesson}

---
"""
        # 如果文件不存在，写入头部
        if not path.exists():
            header = f"# 工作日志 {datetime.now().strftime('%Y-%m-%d')}\n"
            path.write_text(header, encoding="utf-8")

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)

        return str(path)

    def read_recent_episodic(self, days: int = 3) -> str:
        """读取最近N天的情景日志摘要"""
        result = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self.get_episodic_path(date)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                result.append(f"### {date}\n{content}")
        return "\n\n".join(result) if result else "暂无最近日志"

    # ── 语义知识（SQLite） ──

    def add_semantic_fact(self, title: str, fact: str, fact_type: str,
                          source: str = "", agent: str = "unknown",
                          confidence: str = "verified", tags: list = None) -> str:
        """添加一条语义知识"""
        # bug2修复：主键按title+fact内容哈希，不按title
        # 这样同标题不同内容就是不同的ID，不会静默覆盖
        fact_id = f"fact_{hashlib.sha1((title + '|' + fact).encode()).hexdigest()[:8]}"

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO semantic_facts
            (id, title, fact, type, source, agent, date, confidence, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fact_id, title, fact, fact_type, source, agent,
              datetime.now().strftime("%Y-%m-%d"), confidence,
              json.dumps(tags or [])))
        conn.commit()
        conn.close()

        return fact_id

    def search_semantic_facts(self, query: str, limit: int = 5) -> list:
        """
        搜索语义知识（v0.4 关键词权重+显著性加权+时间衰减）

        打分规则：
        - 关键词命中：每个词+1分
        - 标题命中：额外+2分
        - 显著性：critical+3分，important+1分
        - 时间衰减：最近的+分
        """
        import re

        # 简单分词
        keywords = [k.strip() for k in re.split(r'[\s,，。、;；:：]+', query) if k.strip()]

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # bug3修复：默认过滤掉auto_pending（待审知识不进读侧）
        c.execute("SELECT * FROM semantic_facts WHERE confidence != 'auto_pending'")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()

        if not keywords:
            # 没关键词就按时间排
            return rows[:limit]

        # 本地打分
        scored = []
        for row in rows:
            score = 0
            text = (row.get('title', '') + ' ' + row.get('fact', '') + ' ' + row.get('tags', '')).lower()

            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in text:
                    score += 1
                    # 标题命中额外加分
                    if kw_lower in row.get('title', '').lower():
                        score += 2

            # 显著性加权
            fact_type = row.get('type', 'normal')
            if fact_type == 'critical':
                score += 3
            elif fact_type == 'important':
                score += 1

            # 置信度加权
            if row.get('confidence') == 'verified':
                score += 0.5

            if score > 0:
                scored.append((score, row))

        # 按分数排
        scored.sort(key=lambda x: -x[0])

        return [row for score, row in scored[:limit]]

    def search_episodic(self, query: str, days: int = 7, limit: int = 10) -> list:
        """
        搜索情景日志（v0.4新增）

        按关键词+显著性+时间衰减打分
        """
        import re
        from datetime import timedelta

        keywords = [k.strip() for k in re.split(r'[\s,，。、;；:：]+', query) if k.strip()]

        results = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self.get_episodic_path(date)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")

            # 按##分段
            entries = re.split(r'\n## ', content)

            for entry in entries:
                if not entry.strip():
                    continue

                score = 0
                for kw in keywords:
                    if kw.lower() in entry.lower():
                        score += 1

                # 显著性加权
                if '🔴' in entry or '[critical]' in entry:
                    score += 3
                elif '🟡' in entry or '[important]' in entry:
                    score += 1

                # 时间衰减：今天最高
                score += (days - i) * 0.1

                if score > 0:
                    results.append((score, date, entry[:200]))

        results.sort(key=lambda x: -x[0])
        return [{"date": d, "excerpt": e, "score": s} for s, d, e in results[:limit]]

    # ── 会话跟踪（门禁用） ──

    def mark_read_diary(self, session_id: str):
        """标记本次会话已读笔记（v0.6修复：只更新has_read_diary字段，不影响其他标志）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # 先插入空记录（如果不存在）
        c.execute("INSERT OR IGNORE INTO session_log (session_id) VALUES (?)", (session_id,))
        # 只更新需要的字段
        c.execute("""
            UPDATE session_log 
            SET has_read_diary = 1, task_started_at = COALESCE(task_started_at, datetime('now'))
            WHERE session_id = ?
        """, (session_id,))
        conn.commit()
        conn.close()

    def mark_written_diary(self, session_id: str):
        """标记本次会话已写日志（v0.6修复：只更新has_written_diary字段）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO session_log (session_id) VALUES (?)", (session_id,))
        c.execute("""
            UPDATE session_log 
            SET has_written_diary = 1, task_completed_at = datetime('now')
            WHERE session_id = ?
        """, (session_id,))
        conn.commit()
        conn.close()

    def has_read_diary(self, session_id: str) -> bool:
        """检查本次会话是否已读笔记"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT has_read_diary FROM session_log WHERE session_id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0])

    def has_written_diary(self, session_id: str) -> bool:
        """检查本次会话是否已写日志"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT has_written_diary FROM session_log WHERE session_id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0])

    def mark_task_started(self, session_id: str):
        """标记任务开始（执行了工具）（v0.6修复：只更新task_started字段）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO session_log (session_id) VALUES (?)", (session_id,))
        c.execute("""
            UPDATE session_log 
            SET task_started = 1, task_started_at = COALESCE(task_started_at, datetime('now'))
            WHERE session_id = ?
        """, (session_id,))
        conn.commit()
        conn.close()

    def has_task_started(self, session_id: str) -> bool:
        """检查是否启动了任务（执行过工具）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT task_started FROM session_log WHERE session_id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return bool(row and row[0])

    def log_block(self, session_id: str, tool_name: str, reason: str):
        """记录一次拦截事件（审计用）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO block_log (session_id, tool_name, reason)
            VALUES (?, ?, ?)
        """, (session_id, tool_name, reason))
        conn.commit()
        conn.close()

    # ── 审计 ──

    def get_audit_stats(self) -> dict:
        """获取审计统计：今天多少任务读了笔记？多少写了日志？"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM session_log WHERE date(created_at) = date('now')")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM session_log WHERE has_read_diary = 1 AND date(created_at) = date('now')")
        read_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM session_log WHERE has_written_diary = 1 AND date(created_at) = date('now')")
        write_count = c.fetchone()[0]

        conn.close()

        return {
            "total_today": total,
            "read_diary_rate": f"{read_count/total*100:.1f}%" if total else "0%",
            "write_diary_rate": f"{write_count/total*100:.1f}%" if total else "0%",
        }


from datetime import timedelta  # noqa: E402
