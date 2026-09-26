# -*- coding: utf-8 -*-
"""r2 三大修复单测（09-12 晚）：软轨告警/新轮重置/观测器假阳性清零。跑法：容器内 python。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")
sys.path.insert(0, "/deps/outer-workspace")

ok = 0
fail = []


def check(name, cond):
    global ok
    if cond:
        ok += 1
        print(f"  ok {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name}")


# ── 1) 观测器 _write_targets 假阳性清零 ──
from mia_agent.flow_observer import _write_targets  # noqa: E402

t1 = "ls -la /notes 2>/dev/null || echo \"NOT_FOUND\""
check("E2/W2 假阳性: 2>/dev/null 剔除", "/notes" not in _write_targets(t1))
t2 = "echo x > /dev/null"
check("echo 落 /dev/null 剔除", _write_targets(t2) == [])
t3 = "echo hi >> notes/a.md"
check("相对路径正常提取（越界判定在 flags 层）", _write_targets(t3) == ["notes/a.md"])
t4 = "echo hi > /etc/passwd"
check("真越界仍命中", "/etc/passwd" in _write_targets(t4))
t5 = "cat f > /data/mia_home/notes/a.md"
check("数据区内正常放行", "/data/mia_home/notes/a.md" in _write_targets(t5))
t6 = "some_cmd 2>&1 | tee /tmp/x"
check("2>&1 剔除 + tee /tmp 命中",
      "/tmp/x" in [x for x in _write_targets(t6)] and "&1" not in _write_targets(t6))

# ── 2) approvals 软轨 ──
import approvals as ap  # noqa: E402

TID = "t-r2-test"
ap.reset_task_cards(TID)
for i in range(4):
    n = ap.bump_blocked(TID, f"tc-{i}")
    if n > 0:
        ap.bump_warn(TID)
check("硬计 4", ap.task_cards(TID) == 4)
check("软告警 4>=3 出文案", "⚠️" in ap.card_pressure(TID))
# resume 重放同 tc_id：硬轨幂等不变，gate 侧 n>last 不成立（模拟 gate 判据）
n2 = ap.bump_blocked(TID, "tc-0")
check("幂等：重放同 tc 不涨", n2 == 4)
# 爸爸发新消息（human 数 +1）→ 软轨清零、硬轨保留
ap.note_new_turn(TID, 5)
ap.note_new_turn(TID, 6)  # 第二次轮才有效（先建 mark=5 再 >5 才清）
check("新轮后告警清零", ap.card_pressure(TID) == "")
check("硬预算不缩水（防刷）", ap.task_cards(TID) == 4)
# 再烧 3 张 → 告警重新出现
for i in range(3):
    ap.bump_warn(TID)
check("本轮再 3 卡告警复现", "⚠️" in ap.card_pressure(TID))
# 同轮重复 note 不清零
ap.note_new_turn(TID, 6)
check("同轮 note 幂等不清零", "⚠️" in ap.card_pressure(TID))
# 硬预算满 → BUDGET（与软轨无关）
for i in range(ap.CARD_BUDGET):
    ap.bump_blocked(TID, f"x-{i}")
check("硬满走中文强提醒（r33 哨兵退役）", "配额上限" in ap.card_pressure(TID))
ap.reset_task_cards(TID)
check("reset 双轨全清", ap.task_cards(TID) == 0 and ap.card_pressure(TID) == "")

# ── 3) 书记员 REMINDER 退役（路径自适应：容器/宿主两处源码等价）─
import pathlib  # noqa: E402

for p in ("/deps/outer-workspace/src/scribe_hook.py", "D:/m/workspace/scribe_hook.py"):
    f = pathlib.Path(p)
    if f.exists():
        src = f.read_text(encoding="utf-8")
        break
else:
    src = ""
    fail.append("找不到 scribe_hook.py 源码")
check("工具结果注入面零污染（_inject_reminder 已拔）", "_inject_reminder" not in src)
check("WORK_RULES_INJECT 保留（system 侧强制令）", "WORK_RULES_INJECT" in src)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
