# -*- coding: utf-8 -*-
"""
AgentDiary — Rolling Handoff（rolling 交接摘要）

schema v1 §1/§7：
- handoff.md 固定模板 = 冷启动置顶四行：在做 / 卡点 / 下一步 / deadline
- V2 决议：各 agent 一份（共享需求走 refs 链接不合写，防并发覆盖）

用法：
    handoff = DiaryHandoff(store, agent="lyra")
    handoff.update(doing="MVP动代码", blocked="无", next_step="跑lint", deadline="2026-09-20")
    print(handoff.read())
"""

from pathlib import Path


class DiaryHandoff:
    """Rolling 交接摘要——每关键节点覆盖更新，冷启动第一眼就看它"""

    # 四行固定模板（Alice Q1 冷启动置顶，§7）
    TEMPLATE_KEYS = ("doing", "blocked", "next_step", "deadline")
    LABELS = {
        "doing": "在做",
        "blocked": "卡点",
        "next_step": "下一步",
        "deadline": "deadline",
    }

    def __init__(self, store, agent: str = "unknown"):
        self.store = store
        self.agent = agent
        # V2：各 agent 一份 → handoff/<agent>.md（§1 agent 目录层落地时直迁 handoff/<agent>/handoff.md，不返工）
        self.path = Path(store.handoff_dir) / f"{agent}.md"

    def read(self) -> str:
        """读取本 agent 的交接摘要（文件不存在返回空模板说明）"""
        if not self.path.exists():
            return f"（{self.agent} 暂无 handoff——冷启动四行：{ ' / '.join(self.LABELS[k] for k in self.TEMPLATE_KEYS) }）"
        return self.path.read_text(encoding="utf-8")

    def update(self, doing: str = "", blocked: str = "", next_step: str = "",
               deadline: str = "", note: str = "") -> str:
        """
        覆盖更新交接摘要（rolling：每关键节点覆盖更新，Alice 修正①）

        Args:
            doing: 在做
            blocked: 卡点（无则写"无"）
            next_step: 下一步
            deadline: 截止（自由格式，建议日期）
            note: 补充交接细节（可选，追加行，不破坏四行模板）

        Returns:
            写入的 handoff 全文
        """
        lines = [
            f"# Handoff · {self.agent}",
            "",
            f"## {self.LABELS['doing']}",
            doing or "（待更新）",
            "",
            f"## {self.LABELS['blocked']}",
            blocked or "无",
            "",
            f"## {self.LABELS['next_step']}",
            next_step or "（待更新）",
            "",
            f"## {self.LABELS['deadline']}",
            deadline or "（未设）",
        ]
        if note:
            lines += ["", "---", "", f"**交接备注**: {note}"]

        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return self.read()


if __name__ == "__main__":
    # 冒烟测试
    import tempfile
    from .store import DiaryStore

    with tempfile.TemporaryDirectory() as tmp:
        store = DiaryStore(tmp)
        h = DiaryHandoff(store, agent="lyra")
        h.update(doing="写handoff模块", blocked="无", next_step="跑lint", deadline="2026-09-18")
        print(h.read())
        print("\n✅ handoff 冒烟测试通过！")
