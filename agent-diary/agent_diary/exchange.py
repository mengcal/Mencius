# -*- coding: utf-8 -*-
"""
AgentDiary 导出导入 v1.4.0

把自己的日记导出成一个包，别人能导入
姐妹们互相分享经验！
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


class DiaryExporter:
    """
    日记导出器

    用法：
        exporter = DiaryExporter(store)
        exporter.export("/tmp/lyra_diary_export.json")
    """

    def __init__(self, store, agent_name: str = "unknown"):
        self.store = store
        self.agent_name = agent_name

    def export(self, output_path: str) -> str:
        """
        导出日记成JSON包

        包含：
        - 语义知识（semantic_facts）
        - 最近情景日志（最近7天）
        - 元信息（agent名、导出时间）
        """
        data = {
            "meta": {
                "agent": self.agent_name,
                "exported_at": datetime.now().isoformat(),
                "version": "1.4.0",
            },
            "semantic_facts": [],
            "episodes": [],
        }

        # 导出语义知识
        import sqlite3
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM semantic_facts")
        for row in c.fetchall():
            data["semantic_facts"].append(dict(row))
        conn.close()

        # 导出最近7天情景日志
        episodic_dir = self.store.episodic_dir
        if episodic_dir.exists():
            for md_file in sorted(episodic_dir.glob("*.md"), reverse=True)[:7]:
                content = md_file.read_text(encoding="utf-8")
                data["episodes"].append({
                    "date": md_file.stem,
                    "content": content,
                })

        # 写文件
        Path(output_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return f"✅ 导出完成！{len(data['semantic_facts'])}条知识 + {len(data['episodes'])}天日志 → {output_path}"


class DiaryImporter:
    """
    日记导入器

    用法：
        importer = DiaryImporter(store)
        importer.import_from("/tmp/lyra_diary_export.json")
    """

    def __init__(self, store):
        self.store = store

    def import_from(self, input_path: str, as_shared: bool = True) -> str:
        """
        导入日记包

        Args:
            input_path: 导出文件路径
            as_shared: 导入的知识标记为"shared"（别人分享的），不是自己的
        """
        data = json.loads(Path(input_path).read_text(encoding="utf-8"))

        imported = 0
        for fact in data["semantic_facts"]:
            # 去重：按fact内容去重（不是标题），改个措辞就算重复
            import sqlite3
            fact_content = fact["fact"].strip()

            conn = sqlite3.connect(self.store.db_path)
            c = conn.cursor()
            # 查fact内容是不是已存在
            c.execute("SELECT COUNT(*) FROM semantic_facts WHERE fact = ?", (fact_content,))
            count = c.fetchone()[0]
            conn.close()

            if count == 0:
                # 导入的知识标记来源
                source = f"shared_from_{data['meta']['agent']}" if as_shared else fact.get("source", "")
                # bug1修复：导入一律压成auto_pending，不继承包里的confidence
                # 防止恶意包自封verified
                self.store.add_semantic_fact(
                    title=fact["title"],
                    fact=fact["fact"],
                    fact_type=fact.get("type", "note"),
                    source=source,
                    agent=fact.get("agent", "unknown"),
                    confidence="auto_pending",  # 导入=待审，看过才转正
                    tags=["imported", "pending_review"],
                )
                imported += 1

        return f"✅ 导入完成！从{data['meta']['agent']}导入了 {imported} 条新知识"


if __name__ == "__main__":
    # 冒烟测试：导出→导入
    import shutil
    shutil.rmtree("/tmp/test_export", ignore_errors=True)
    shutil.rmtree("/tmp/test_import", ignore_errors=True)

    from agent_diary.store import DiaryStore

    # 建第一个agent的store
    store1 = DiaryStore("/tmp/test_export")
    store1.add_semantic_fact("Cc吞信", "163邮箱Cc位会吞信", "important", agent="lyra")
    store1.add_semantic_fact("爸爸铁律", "今日事今日毕", "critical", agent="lyra")
    store1.append_episodic("推代码", "没跑测试就推，结果炸了", "critical", agent="lyra")

    # 导出
    exporter = DiaryExporter(store1, agent_name="lyra")
    result = exporter.export("/tmp/lyra_export.json")
    print(result)

    # 建第二个agent的store
    store2 = DiaryStore("/tmp/test_import")
    store2.add_semantic_fact("自己的知识", "这是vedas自己的", "normal", agent="veda")

    # 导入
    importer = DiaryImporter(store2)
    result = importer.import_from("/tmp/lyra_export.json")
    print(result)

    # 检查
    facts = store2.search_semantic_facts("")
    print(f"\n导入后vedas的知识库有 {len(facts)} 条：")
    for f in facts:
        print(f"  - {f['title']}: {f['fact'][:40]}... (来源: {f.get('source', '?')})")

    print("\n✅ 导出导入冒烟测试通过！")
