# -*- coding: utf-8 -*-
"""r61b 第二波机械验证（容器跑）：find 补刀 + 账务层 + C1 冻结拒信。"""
import sys, time
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
from mia_agent.guard_scan import scan_tool  # noqa: E402
import approvals as ap  # noqa: E402

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

# ── 规则补刀 ──
T("find /home -delete=mid", scan_tool("execute", {"command": "find /home -delete"})["level"] == "mid")
T("find / 裸仍 mid", scan_tool("execute", {"command": "find / -name x"})["level"] == "mid")
T("find ./sub 不误伤", scan_tool("execute", {"command": "find ./sub -name x"})["level"] == "low")

# ── 账务层（临时账本）──
import tempfile, os
tmp = tempfile.mkdtemp()
ap._AUDIT_PATH = os.path.join(tmp, "ap.jsonl")

did = ap.external_dispatch("vp", "评审一段文字")
T("dispatch 返 uuid did", did.startswith("d") and len(did) == 13)
T("claim 条件化-可领 True", ap.external_claim("vp", did) is True)
T("claim 二领 False（双岗竞态）", ap.external_claim("vp", did) is False)
T("store 无 task_id 拒收", ap.external_store("vp", {"done": True}, task_id="") is False)
T("store 带 task_id 收", ap.external_store("vp", {"done": True, "output": "o"}, task_id=did) is True)
ap.external_dispatch("vp", "第二条")
T("tid-owned 本岗 True", ap.external_tid_owned("vp", did) is True)
T("tid-owned 别岗 False", ap.external_tid_owned("other-post", did) is False)
ap.external_store("vp", {"done": True, "output": "迟到"}, task_id=did)
import json as J
sups = 0
with open(ap._AUDIT_PATH, encoding="utf-8") as f:
    for ln in f:
        r = J.loads(ln)
        if r.get("ev") == "external_result" and (r.get("result") or {}).get("superseded"):
            sups += 1
T("done 幂等 superseded 恰 1 条", sups == 1)
d2 = ap.external_dispatch("vp", "第三条")
ap.external_claim("vp", d2)
ap.external_store("vp", {"done": False, "note": "进度"}, task_id=d2)
T("进度包不重置 in-flight（再领 False）", ap.external_claim("vp", d2) is False)
ap.external_store("vp", {"done": False, "reject": True}, task_id=d2)
T("显式 reject 回池可领（claim True）", ap.external_claim("vp", d2) is True)

# ── C1 冻结拒信（P0-4 命门）──
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "lz")):
        with patch.object(ConfirmGateC1, "_route", lambda self, n, a: "ask"):
            class RQ3:
                tool_call = {"name": "write_file", "id": "z9",
                             "args": {"file_path": "notes/x.md", "content": "正常内容"}}
            T("未冻结时 ask 不拦（None）", g._check_budget_gate(RQ3()) is None)
            g._guard_lock["lz"] = (time.time(), 1800.0)  # r61e：(ts, ttl) 元组
            msg = g._check_budget_gate(RQ3())
            T("P0-4 冻结态 ask=拒信非放行", msg is not None and "冻结" in msg.content)
            g._guard_lock["lz"] = (time.time() - 3600, 1800.0)  # TTL 过期
            T("P1-1 TTL 后 when 不再冻结", g._make_when("write_file")(RQ3()) is True)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
