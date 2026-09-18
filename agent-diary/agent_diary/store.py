# -*- coding: utf-8 -*-
"""
AgentDiary — 存储层

三层记忆：
1. 情景日志（Episodic Log）：按时间记录的原始事件流，Markdown文件
2. 语义知识（Semantic Facts）：从事件中抽象的规则/事实，SQLite
3. 程序手册（Procedural Skills）：可复用工作流，Markdown

格式标准：schema v1（docs/schema-v1-draft.md，RC2 已落票果）
- 情景日志条目 = frontmatter（id/author/kind/significance/private/source/confidence/refs/open_question）
- 审计事件 = JSONL 流（§5，reason_code 稳定枚举）
"""

import os
import re
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

# §5 审计 reason_code 稳定枚举（RC2 收编，聚类分析靠码、人读理由放 note）
REASON_CODES = {
    "read_not_done",        # 执行类工具调用前无 read 记录，硬拒
    "log_not_done",         # task_started 后未 write，收工判定不过
    "gate_error_closed",    # 门禁自身异常，fail-closed 拒
    "promote",              # pending → verified 晋升
    "reject",               # pending 拒绝（删除）
    "import_pending",       # 导入压 pending（含指令模式命中打 flag）
    "bypass_suspect",       # 旁路嫌疑：execution 放行但 session 无 read 记录
}
GATE_VERSION = "1.3.0-mvp1"  # §5 gate_version 审计戳


class DiaryStore:
    """工作日志存储层"""

    def __init__(self, base_dir: str = "./diary_data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.episodic_dir = self.base_dir / "episodic"
        self.semantic_dir = self.base_dir / "semantic"
        self.procedural_dir = self.base_dir / "procedural"
        self.handoff_dir = self.base_dir / "handoff"      # rolling 交接（各 agent 一份，V2 决议）
        self.audit_dir = self.base_dir / "audit"          # §5 JSONL 审计事件流

        for d in [self.episodic_dir, self.semantic_dir, self.procedural_dir,
                  self.handoff_dir, self.audit_dir]:
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

        # §6 migration：semantic_facts 加结构化 private 列（幂等；三关全跳=巩固/晋升/导出）
        sf_cols = [r[1] for r in c.execute("PRAGMA table_info(semantic_facts)").fetchall()]
        if "private" not in sf_cols:
            c.execute("ALTER TABLE semantic_facts ADD COLUMN private INTEGER DEFAULT 0")

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

        # §5 migration：block_log 加 reason_code / note / gate_version（幂等，老库升级不炸）
        cols = [r[1] for r in c.execute("PRAGMA table_info(block_log)").fetchall()]
        if "reason_code" not in cols:
            c.execute("ALTER TABLE block_log ADD COLUMN reason_code TEXT DEFAULT ''")
        if "note" not in cols:
            c.execute("ALTER TABLE block_log ADD COLUMN note TEXT DEFAULT ''")
        if "gate_version" not in cols:
            c.execute("ALTER TABLE block_log ADD COLUMN gate_version TEXT DEFAULT ''")

        conn.commit()
        conn.close()

    # ── 情景日志（Markdown） ──

    def get_episodic_path(self, date: Optional[str] = None) -> Path:
        """获取某天的情景日志文件路径"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.episodic_dir / f"{date}.md"

    def _next_entry_id(self, agent: str, date: str) -> str:
        """
        生成条目 id：`{agent}-{YYYYMMDD}-{NNN}`（§2，正则 ^[a-z]+-\\d{8}-\\d{3}$）

        规则：扫描当天文件已有同 agent 条目的最大序号 +1，撞号=0（§8 lint 判据面）。
        """
        date_compact = date.replace("-", "")
        path = self.get_episodic_path(date)
        max_seq = 0
        if path.exists():
            pattern = re.compile(rf"{re.escape(agent)}-{date_compact}-(\d{{3}})")
            for m in pattern.finditer(path.read_text(encoding="utf-8")):
                seq = int(m.group(1))
                if seq > max_seq:
                    max_seq = seq
        return f"{agent}-{date_compact}-{max_seq + 1:03d}"

    def append_episodic(
        self,
        event: str,
        lesson: str,
        significance: str = "normal",
        agent: str = "unknown",
        context: str = "",
        kind: str = "lesson",
        private: bool = False,
        refs: Optional[List[str]] = None,
        open_question: str = "",
        source_channel: str = "session",
        source_origin: str = "",
        confidence: str = "verified",
    ) -> str:
        """
        追加一条情景日志（schema v1 §2 frontmatter 格式）

        Args:
            event: 发生了什么事？（事件一句话）
            lesson: 学到了什么教训/为什么/结果（理由原文保留，不许压成一行结论）
            significance: critical/important/normal
            agent: 写入侧盖章（server 端派生优先，客户端自报降权）
            context: 当时的上下文
            kind: lesson|decision|pitfall|rule|promise|question
            private: true=永不进共享层/导出/巩固（三关全跳）
            refs: 关联条目 id 列表
            open_question: 悬念字段（V4 决议：埋但可选非必填，lint 允许缺失）
            source_channel: mail|issue|session|import
            source_origin: 来源原文描述
            confidence: verified=本人写入；auto_pending=机器提名/导入（不许直写 canon）

        Returns:
            条目文件路径
        """
        date = datetime.now().strftime("%Y-%m-%d")
        path = self.get_episodic_path(date)
        now = datetime.now().astimezone()  # 带时区（UTC 混账教训，issue #4）
        entry_id = self._next_entry_id(agent, date)

        entry = f"""
<!-- entry: {entry_id} -->
---
id: {entry_id}
author: {agent}
kind: {kind}
significance: {significance}
private: {'true' if private else 'false'}
source:
  channel: {source_channel}
  origin: "{source_origin}"
  date: {now.isoformat()}
  chain: direct
confidence: {confidence}
refs: {json.dumps(refs or [], ensure_ascii=False)}
open_question: "{open_question}"
---

**事件**: {event}

**上下文**: {context if context else '-'}

**教训/结果**: {lesson}

---
"""
        # 如果文件不存在，写入头部
        if not path.exists():
            header = f"# 工作日志 {date}\n"
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
                          confidence: str = "verified", tags: list = None,
                          private: bool = False) -> str:
        """添加一条语义知识（§6：private=True 三关全跳——巩固/晋升/导出）"""
        # bug2修复：主键按title+fact内容哈希，不按title
        # 这样同标题不同内容就是不同的ID，不会静默覆盖
        fact_id = f"fact_{hashlib.sha1((title + '|' + fact).encode()).hexdigest()[:8]}"

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO semantic_facts
            (id, title, fact, type, source, agent, date, confidence, tags, private)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fact_id, title, fact, fact_type, source, agent,
              datetime.now().strftime("%Y-%m-%d"), confidence,
              json.dumps(tags or []), 1 if private else 0))
        conn.commit()
        conn.close()

        return fact_id

    def get_fact_confidence(self, fact_id: str) -> str:
        """
        v1.2.0 P1第二层：按id查一条语义知识的置信度

        向量路径防御性过滤用——索引可能过期/被增量添加绕过，
        读侧永远以库里最新confidence为准。
        """
        if not fact_id:
            return ""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT confidence FROM semantic_facts WHERE id = ?", (fact_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else ""

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

            # 只有关键词命中的条目才参与排序（显著性/置信度仅作加权，
            # 不能让无关 critical 条目无命中也被返回——MVP 测试暴露的既有 bug）
            if score > 0:
                fact_type = row.get('type', 'normal')
                if fact_type == 'critical':
                    score += 3
                elif fact_type == 'important':
                    score += 1
                if row.get('confidence') == 'verified':
                    score += 0.5
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

            # 分段：兼容两种格式——旧版 `## HH:MM ...` 段头、新版 `<!-- entry: ... -->` frontmatter 条目
            entries = re.split(r'\n(?=## |<!-- entry:)', content)

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

    def log_block(self, session_id: str, tool_name: str, reason: str,
                  reason_code: str = "", note: str = "") -> None:
        """
        记录一次拦截事件（审计用，§5）

        reason_code 用稳定枚举（REASON_CODES），人读理由放 note，聚类分析靠码。
        同事件同步落一行 JSONL 审计流（audit/events.jsonl）。
        """
        if reason_code not in REASON_CODES and reason_code:
            reason_code = ""  # 非法枚举不落码，宁缺毋滥
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO block_log (session_id, tool_name, reason, reason_code, note, gate_version)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, tool_name, reason, reason_code, note, GATE_VERSION))
        conn.commit()
        conn.close()
        self.append_audit_event(session_id, tool_name, "block", reason_code or reason,
                                note, GATE_VERSION)

    def append_audit_event(self, session_id: str, tool: str, decision: str,
                           reason_code: str, note: str, gate_version: str) -> None:
        """
        §5 审计事件：每次拦截/放行/晋升落一行 JSONL

        {ts, session, tool, decision, reason_code, gate_version}
        """
        event = {
            "ts": datetime.now().astimezone().isoformat(),
            "session": session_id,
            "tool": tool,
            "decision": decision,          # block | pass | promote | reject | import_pending
            "reason_code": reason_code,
            "gate_version": gate_version,
        }
        if note:
            event["note"] = note
        with open(self.audit_dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

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
