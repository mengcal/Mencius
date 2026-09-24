# -*- coding: utf-8 -*-
"""r44b 单测：task_brief 新判定 + 软重置衰减 + 契约 + hy4 病例全复现。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent import task_brief as tb  # noqa: E402
import approvals as ap  # noqa: E402
from mia_agent.acceptance_kit import extract_literals, literal_diff  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


def _new(tb, ap, tid):
    tb._briefs.pop(tid, None)
    ap.reset_task_cards(tid)


# ── 1) 新-target 判定（P0-2）──
tb._briefs.clear()
b1 = tb.note_task("把 notes/a.md 里『TODO』改成『已完成』", "tA", 1)
T("A 首轮 new+三 role", b1["new"] and dict((l["value"], l["role"]) for l in b1["literals"]).get("TODO") == "old-value")
b2 = tb.note_task("继续", "tA", 2)
T("'继续'=同任务", (not b2["new"]) and (not b2["clarify"]))
b3 = tb.note_task("看一下 notes/a.md 现在的样子", "tA", 3)
T("窄化追问（a.md 已在场）=不换题不回血", not b3["new"])
b4 = tb.note_task("删掉它", "tA", 4)
T("'删掉它'动词跳变=换题（hy4 Q1 病例）", b4["new"] and b4["clarify"])
b5 = tb.note_task("写 notes/b.md 存纪要", "tB", 1)
T("B 首轮 new", b5["new"])
b6 = tb.note_task("再写 notes/b.md 补一行", "tB", 2)
T("同目标同动词类=同任务", not b6["new"])

# ── 2) 软重置衰减（P1-6/Q3 最坏路径封堵）──
ap._soft_resets.clear()
TID = "tR"
ap.reset_task_cards(TID)
for i in range(8):
    ap.bump_blocked(TID, f"c{i}")
T("烧满 8=BUDGET", ap.card_pressure(TID) == "BUDGET")
T("第1次回血到4", ap.soft_reset_task(TID) and ap.task_cards(TID) == 4)
for i in range(4):
    ap.bump_blocked(TID, f"d{i}")
T("回血后再烧满 8", ap.card_pressure(TID) == "BUDGET")
ap.soft_reset_task(TID)
T("第2次回血到3（衰减）", ap.task_cards(TID) == 3)
ap.soft_reset_task(TID)
T("第3次回血到2（逐次衰减）", ap.task_cards(TID) == 2)
ap.soft_reset_task(TID)
T("第4次回血到1", ap.task_cards(TID) == 1)
ap.soft_reset_task(TID)
T("第5次回血=0（不再给）", ap.task_cards(TID) == 1)
for i in range(8):
    ap.bump_blocked(TID, f"e{i}")
T("烧回 8 后回血不再生效", ap.card_pressure(TID) == "BUDGET" and not ap.soft_reset_task(TID))
ap.reset_task_cards(TID)

# ── 3) 验收契约（P0-1）：acceptance_for→literal_diff 直通 ──
tb._briefs.clear()
tb.note_task(r"写 notes/report.md，内容含 D:\m\workspace", "tD", 1)
items = tb.acceptance_for("tD")
T("acceptance_for 返回 dict 列表", items and all(isinstance(i, dict) and "value" in i for i in items))
miss = literal_diff(items, "notes/report.md\nD:\\workspace 少了m")
T("机械核对逮住缺段（含 report.md 在场不误报）",
   len(miss) == 1 and miss[0]["value"] == "D:\\m\\workspace")

# ── 4) FORBID 扩词（P2-13）──
r = extract_literals("删掉 notes/old.md 这个文件")
roles = dict(r["paths"])
T("'删掉X'的 X 标 forbidden", roles.get("notes/old.md") == "forbidden")

# ── 5) clarify 铁律：空 sig 写类追问不继承"已明确" ──
tb._briefs.clear()
tb.note_task("新建 notes/c.md 记录要点", "tE", 1)
c2 = tb.note_task("再加一份 notes/d.md 的备份，删掉旧版", "tE", 2)
T("新目标出现=new", c2["new"])
c3 = tb.note_task("清空它", "tE", 3)
T("空 sig 动词跳变→换题+clarify（不拿旧账验收）", c3["new"] and c3["clarify"])

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
