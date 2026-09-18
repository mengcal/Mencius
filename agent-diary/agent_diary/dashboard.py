# -*- coding: utf-8 -*-
"""
AgentDiary — 审计仪表盘 v0.3

一行命令看清楚：
- 今天多少任务读了笔记？
- 多少写了日志？
- 门禁拦截了多少次？
- 拦截率多少？
- 哪些工具最常被拦？

拦截数=0本身就是告警——说明门禁没生效！
"""

from typing import Optional
from .store import DiaryStore


class AuditDashboard:
    """审计仪表盘——看门禁工作得好不好"""

    def __init__(self, store: DiaryStore):
        self.store = store

    def _count_gate_events_today(self):
        """
        v1.3.1：统计今天审计流里的门禁事件（pass/block）

        判断"门禁是否接入"用——纯 CLI/库直写模式没有门禁事件，
        "拦截=0"就不该告警"门禁没生效"（那是正常直写）。
        """
        import json as _json
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        gate_pass = gate_block = 0
        audit_file = self.store.audit_dir / "events.jsonl"
        if not audit_file.exists():
            return 0, 0
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = _json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("ts", "")[:10] != today:
                        continue
                    dec = ev.get("decision", "")
                    if dec == "pass":
                        gate_pass += 1
                    elif dec == "block":
                        gate_block += 1
        except OSError:
            return 0, 0
        return gate_pass, gate_block

    def report(self, date: Optional[str] = None) -> str:
        """
        生成审计报告

        Args:
            date: 日期（YYYY-MM-DD），默认今天
        """
        import sqlite3
        from datetime import datetime, timedelta

        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 日期过滤
        date_filter = ""
        params = []
        if date:
            date_filter = "WHERE date(created_at) = ?"
            params = [date]

        # 总任务数
        c.execute(f"SELECT COUNT(*) as cnt FROM session_log {date_filter}", params)
        total_sessions = c.fetchone()["cnt"]

        # 读了笔记的
        c.execute(f"SELECT COUNT(*) as cnt FROM session_log WHERE has_read_diary = 1 {date_filter.replace('WHERE', 'AND') if date_filter else ''}", params)
        # 简化一下，直接查
        c.execute("SELECT COUNT(*) as cnt FROM session_log WHERE has_read_diary = 1" + (f" AND date(created_at) = ?" if date else ""), params)
        read_count = c.fetchone()["cnt"]

        # 写了日志的
        c.execute("SELECT COUNT(*) as cnt FROM session_log WHERE has_written_diary = 1" + (f" AND date(created_at) = ?" if date else ""), params)
        write_count = c.fetchone()["cnt"]

        # 拦截统计
        c.execute("SELECT COUNT(*) as cnt FROM block_log" + (f" WHERE date(created_at) = ?" if date else ""), params)
        block_count = c.fetchone()["cnt"]

        # 最常被拦的工具
        c.execute("""
            SELECT tool_name, COUNT(*) as cnt 
            FROM block_log 
            """ + (f"WHERE date(created_at) = ?" if date else "") + """
            GROUP BY tool_name 
            ORDER BY cnt DESC 
            LIMIT 5
        """, params)
        top_blocked = [dict(r) for r in c.fetchall()]

        # 拦截原因分布
        c.execute("""
            SELECT reason, COUNT(*) as cnt 
            FROM block_log 
            """ + (f"WHERE date(created_at) = ?" if date else "") + """
            GROUP BY reason 
            ORDER BY cnt DESC
        """, params)
        reasons = [dict(r) for r in c.fetchall()]

        conn.close()

        # 计算比率
        read_rate = f"{read_count/total_sessions*100:.1f}%" if total_sessions else "0%"
        write_rate = f"{write_count/total_sessions*100:.1f}%" if total_sessions else "0%"

        # v1.3.1：告警只在"门禁已接入"时有效——纯 CLI/库直写模式不误报
        gate_pass, gate_block = self._count_gate_events_today()
        gate_active = (gate_pass + gate_block) > 0
        alert = ""
        if total_sessions > 0 and block_count == 0 and gate_active:
            alert = ("\n\n⚠️ 告警：今天有 {} 个任务，拦截数为0，但门禁有放行记录——"
                     "拦截可能没生效！".format(total_sessions))
        elif total_sessions > 0 and not gate_active:
            alert = ("\n\nℹ️ 提示：今天有 {} 个任务，但无门禁事件——"
                     "当前为 CLI/纯库直写模式（门禁未接入），拦截=0 属正常直写。".format(total_sessions))

        # 生成报告
        report = f"""
📊 AgentDiary 审计仪表盘
{'='*40}
日期: {date or datetime.now().strftime('%Y-%m-%d')}

📈 总体数据:
  总任务数: {total_sessions}
  读了笔记: {read_count} ({read_rate})
  写了日志: {write_count} ({write_rate})

🚫 门禁拦截:
  总拦截次数: {block_count}
"""

        if top_blocked:
            report += "\n🔝 最常被拦的工具:\n"
            for item in top_blocked:
                report += f"  - {item['tool_name']}: {item['cnt']}次\n"

        if reasons:
            report += "\n📋 拦截原因分布:\n"
            for item in reasons:
                report += f"  - {item['reason']}: {item['cnt']}次\n"

        report += alert

        return report.strip()

    def summary(self) -> dict:
        """机器可读的摘要"""
        import sqlite3
        conn = sqlite3.connect(self.store.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM session_log WHERE date(created_at) = date('now')")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM session_log WHERE has_read_diary = 1 AND date(created_at) = date('now')")
        read = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM session_log WHERE has_written_diary = 1 AND date(created_at) = date('now')")
        write = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM block_log WHERE date(created_at) = date('now')")
        blocks = c.fetchone()[0]

        conn.close()

        # v1.3.1：同 report() 口径——门禁未接入时 alert 不置位
        gate_pass, gate_block = self._count_gate_events_today()
        gate_active = (gate_pass + gate_block) > 0

        return {
            "total_today": total,
            "read_today": read,
            "write_today": write,
            "block_today": blocks,
            "gate_active": gate_active,
            "alert": total > 0 and blocks == 0 and gate_active,
        }
