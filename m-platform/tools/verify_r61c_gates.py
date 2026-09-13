# -*- coding: utf-8 -*-
"""r61c 门层+账务验证（容器内跑；HTTP 全链由 bash+curl 配置件另跑）。"""
import sys, time, json
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
import approvals as ap  # noqa: E402

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

# ── N1（P0）：无 tid 线程 high 必须吃拒信，不得放行 ──
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "")):
        class R:
            tool_call = {"name": "execute", "id": "n1a", "args": {"command": "rm -rf /"}}
        w = g._make_when("execute")
        T("N1 when 拦（False）", w(R()) is False)
        msg = g._check_budget_gate(R())
        T("N1 无 tid 也吃拒信（不再敞怀）", msg is not None and "机器安全门" in msg.content)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "fz")):
        g._guard_lock["fz"] = (time.time(), 1800.0)  # r61e：锁值 (ts, ttl) 元组化
        class RQ:
            tool_call = {"name": "write_file", "id": "z9",
                         "args": {"file_path": "notes/ok.md", "content": "正常"}}
        m2 = g._check_budget_gate(RQ())
        T("冻结 ask=拒信", m2 is not None and "冻结" in m2.content)
        g._guard_deny["fz"] = {"ghost"}
        g._guard_lock["fz"] = (time.time() - 3600, 1800.0)
        T("_frozen TTL 自愈清残留", g._frozen("fz") is False and "ghost" not in (g._guard_deny.get("fz") or set()))

# ── N9：尾窗挤出（大噪声账后归属/幂等判定仍对）──
import tempfile, os
tmp = tempfile.mkdtemp(); ap._AUDIT_PATH = os.path.join(tmp, "a.jsonl")
did = ap.external_dispatch("np", "老单等回调")
with ap._audit_lock:
    for i in range(4000):
        ap._audit("guard_mid", thread_id=f"noise{i}", tool="execute", why="x" * 60)
T("N9 大账后 tid_owned 仍 True", ap.external_tid_owned("np", did) is True)
ap.external_store("np", {"done": True, "output": "o"}, task_id=did)
ap.external_store("np", {"done": True, "output": "late"}, task_id=did)
sups = sum(1 for ln in open(ap._AUDIT_PATH, encoding="utf-8")
           if (lambda r: r.get("ev") == "external_result" and (r.get("result") or {}).get("superseded"))(json.loads(ln)))
T("N9 superseded 全史判定对", sups == 1)

# ── N17：脏 ts 不炸 ──
with open(ap._AUDIT_PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": "not-a-number", "ev": "external_claim", "tid": did, "tool": "np"}) + "\n")
try:
    ap.external_pending_view("np")
    T("N17 脏 ts 不炸", True)
except Exception:
    T("N17 脏 ts 不炸", False)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
