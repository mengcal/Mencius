# -*- coding: utf-8 -*-
"""r45 PlanCheck 单测：验收导航注入/clarify 路由/同型×3 连撞提醒。"""
import sys, types
sys.path.insert(0, "/deps/outer-workspace/src")

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


from mia_agent import task_brief as tb  # noqa: E402
from mia_agent.flow_observer import observer  # noqa: E402
from mia_agent.plan_check import PlanCheckMiddleware  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

# ── 1) 验收导航注入 ──
tb._briefs.clear()
TID = "pc-t1"
observer._runs[TID] = []


class _Cfg:
    configurable = {"thread_id": TID}


import langgraph.config as _lg
_orig = _lg.get_config
_lg.get_config = lambda: {"configurable": {"thread_id": TID}}

tb.note_task("统计 notes/ 各文件行数写入 notes/stats.md", TID, 1)


class Req:
    system_prompt = ""


pc = PlanCheckMiddleware()
req1 = Req()
pc._inject(req1)
T("验收导航进 system", "验收导航" in req1.system_prompt and "notes/stats.md" in req1.system_prompt)
T("两栏汇报指令在", "任务要的是 X" in req1.system_prompt)

# ── 2) clarify 路由 ──
tb._briefs.clear()
r2 = tb.note_task("帮我整理下笔记", TID, 2)
req2 = Req()
pc._inject(req2)
T("clarify 提示进 system（问是免费的）", r2["clarify"] and "先问爸爸" in req2.system_prompt)

# ── 3) 同型×3 连撞（C5 复现场景：out-of-scope:/notes 三连）──
observer._runs[TID] = [
    {"tool": "execute", "fp": "a1", "ts": 1, "flags": ["out-of-scope:/notes/"]},
    {"tool": "execute", "fp": "a2", "ts": 2, "flags": ["out-of-scope:/notes/x"]},
    {"tool": "execute", "fp": "a3", "ts": 3, "flags": ["out-of-scope:/notes/y.md"]},
]
res = pc._check_streak({"messages": []})
T("三连撞返回提醒消息", res and "连撞 3 次" in str(res) and "相对路径 notes/" in str(res))
observer._runs[TID] = [
    {"tool": "execute", "fp": "b1", "ts": 1, "flags": ["out-of-scope:/notes/"]},
    {"tool": "execute", "fp": "b2", "ts": 2, "flags": []},
    {"tool": "execute", "fp": "b3", "ts": 3, "flags": ["out-of-scope:/tmp"]},
]
T("非同型不触发", pc._check_streak({"messages": []}) is None)

_lg.get_config = _orig
tb._briefs.clear()
observer._runs.pop(TID, None)
print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
