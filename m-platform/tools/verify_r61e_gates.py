# -*- coding: utf-8 -*-
"""r61e 门层+HTTP nonce/claimed 链验证（容器内跑；HTTP 用 http.client 字面量直连）。"""
import sys, time, json, os, http.client
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
import approvals as ap  # noqa: E402

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

# ── 1. fail-closed（Cora N2+NOVA：guard 崩溃≠放行）──
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402
import mia_agent.guard_scan as _gs  # noqa: E402
import tempfile
tmp = tempfile.mkdtemp(); ap._AUDIT_PATH = os.path.join(tmp, "a.jsonl")
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "fc")):
        def boom(tool, args):
            raise RuntimeError("模拟 guard 崩溃")
        with patch.object(_gs, "scan_tool", boom):
            class R:
                tool_call = {"name": "execute", "id": "f1", "args": {"command": "ls"}}
            w = g._make_when("execute")
            T("崩溃 when 不放行（False）", w(R()) is False)
            msg = g._check_budget_gate(R())
            T("崩溃调用吃拒信（fail-closed）", msg is not None and "机器安全门" in msg.content)
        crash = [l for l in open(ap._AUDIT_PATH, encoding="utf-8") if "guard_crash" in l]
        T("guard_crash 落账（不静默）", len(crash) >= 1)
        T("guard_crash 只存异常类名（脱敏）", "模拟" not in "".join(crash))

        # ── 2. TTL 退避（NOVA①）：30m→1h→永久 ──
        for i in range(3):
            g._guard_streak["fc"] = [time.time(), time.time()]
            with patch.object(_gs, "scan_tool", lambda t, a: {"level": "high", "findings": [("high", "x")]}):
                class RH:
                    tool_call = {"name": "execute", "id": f"h{i}", "args": {"command": "rm -rf /"}}
                g._make_when("execute")(RH())
        T("三次冻结计数=3", g._guard_freeze_n["fc"] == 3)
        T("第 3 次冻结=永久锁", g._guard_lock["fc"][1] == float("inf"))

        # ── 3. 空 tc_id 退指纹不连坐（Cora N3）──
        g2 = ConfirmGateC1()
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "kt")):
            class RA:
                tool_call = {"name": "execute", "id": "", "args": {"command": "rm -rf /"}}
            class RB:
                tool_call = {"name": "execute", "id": "", "args": {"command": "dd if=x of=/dev/sda"}}
            g2._make_when("execute")(RA())
            denied = g2._guard_deny.get("kt", set())
            T("空 id 登记为指纹键", len(denied) == 1 and list(denied)[0].startswith("fp:"))
            mB = g2._check_budget_gate(RB())
            T("B 不被 A 的登记连坐", mB is None)

print("PART1 门层完成")

# ── r61f D 组（hy4 五轮 18 格）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    # D13 TTL 中间档：n=1→1800、n=2→3600（只断 n=3 证不了公式）
    g3 = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d13")):
        for i, want in enumerate((1800.0, 3600.0)):
            g3._guard_streak["d13"] = [time.time(), time.time()]
            with patch.object(_gs, "scan_tool", lambda t, a: {"level": "high", "findings": [("high", "x")]}):
                class RH3:
                    tool_call = {"name": "execute", "id": f"q{i}", "args": {"command": "rm -rf /"}}
                g3._make_when("execute")(RH3())
            T(f"D13 n={i+1} ttl={want}", g3._guard_lock["d13"][1] == want)
    # D15 空 id 命中侧：同参数第二次（空 id）必须被同一指纹拒
    g4 = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d15")):
        class RS1:
            tool_call = {"name": "execute", "id": "", "args": {"command": "rm -rf /x"}}
        with patch.object(_gs, "scan_tool", lambda t, a: {"level": "high", "findings": [("high", "x")]}):
            g4._make_when("execute")(RS1())
        m2 = g4._check_budget_gate(RS1())
        T("D15 同参二次=拒（命中侧）", m2 is not None and "机器安全门" in m2.content)
        class RS2:
            tool_call = {"name": "execute", "id": "", "args": {"command": "rm -rf /y"}}
        T("D15 异参不误伤", g4._check_budget_gate(RS2()) is None)

# ── E17 来源双态四分支 + rids 脱敏断言 ──
from office.routers.external import _callback_source
import os as _os
class _C:
    def __init__(s, h): s.client = type("c", (), {"host": h})()
_os.environ.pop("MIA_EXTERNAL_SOURCES", None)
ok1, c1 = _callback_source(_C("172.18.0.9"))   # 邻居容器 IP（非 .1 结尾）
T("E17a 观测态邻居IP=observed-other", (ok1, c1) == (True, "observed-other"))
ok2, c2 = _callback_source(_C("172.17.0.1"))
T("E17b 网关IP=observed-bridge", (ok2, c2) == (True, "observed-bridge"))
_os.environ["MIA_EXTERNAL_SOURCES"] = "172.17.0.1"
ok3, c3 = _callback_source(_C("172.18.0.9"))
T("E17c 强制态不在列表=reject-enforce", (ok3, c3) == (False, "reject-enforce"))
ok4, c4 = _callback_source(_C("172.17.0.1"))
T("E17d 强制态在列表=env-list", (ok4, c4) == (True, "env-list"))
_os.environ.pop("MIA_EXTERNAL_SOURCES", None)
# rids 断言：guard_mid/dispatch_blocked/隔离体账里不得出现规则人话，rids 为 8 位 hex
import re as _re
lines = open(ap._AUDIT_PATH, encoding="utf-8").read()
d = ap.external_dispatch("ridpost", "rm -rf / 危险任务应被拒派")
T("E17e dispatch_blocked 存 rids 无明文",
    "递归强制删除" not in open(ap._AUDIT_PATH, encoding="utf-8").read()[len(lines):]
    and '"rids"' in open(ap._AUDIT_PATH, encoding="utf-8").read()[len(lines):])
ap.external_store("ridpost", {"done": True, "output": "x" * 10}, task_id="dtid1")
q = ap.external_store("ridpost", {"output": "-----BEGIN " + "PRIVATE KEY-----\nzz"}, task_id="dtid2")
tail2 = open(ap._AUDIT_PATH, encoding="utf-8").read()
T("E17f 隔离体存 rids（私钥人话不回流）", "私钥内容" not in tail2 and '"quarantined"' in tail2)
T("E17g rids 格式=8位hex", bool(_re.search(r'"rids": \["[0-9a-f]{8}"', tail2)))

# ── 4. HTTP nonce/claimed 链（Cora N6+Lyra②）──
# 注意：服务端读真账——本进程账路径必须还原，否则 dispatch 落临时件、
# 服务器看不见单（06:2x 首跑 4 连 FAIL 的根因，测试自身的环境错位）。
ap._AUDIT_PATH = None  # 还原惰性真值
from mia_agent.external_guard import hkdf_subkey
from settings_mgr import secret_get
mk = (secret_get("external.master_key") or "").encode("utf-8")
if not mk:
    print("NOKEY"); sys.exit(1)
SK = hkdf_subkey(mk, "cb-post").hex()
def _req(method, path, body=None):  # 名字避开 http 模块遮蔽
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=20)
    hdrs = {"Authorization": "Bearer " + SK, "Content-Type": "application/json"}
    c.request(method, path, json.dumps(body) if body is not None else None, hdrs)
    try:
        return json.loads(c.getresponse().read().decode())
    except Exception:
        return {"raw": "?"}
    finally:
        c.close()

d = ap.external_dispatch("cb-post", "nonce 链验证单")
d2 = ap.external_dispatch("cb-post", "nonce 唯一性对照单")
_pv = _req("GET", "/external/pending/cb-post")
_ns = {t["id"]: t.get("nonce", "") for t in (_pv.get("tasks") or [])}
T("D16 nonce 跨任务唯一", _ns.get(d, "x") != _ns.get(d2, "x") and len(_ns.get(d, "")) == 8)
_req("POST", "/external/claim/cb-post", {"task_id": d2})
_req("POST", "/external/callback/cb-post", {"done": True, "task_id": d2,
      "ts": time.time(), "nonce": _ns.get(d2, "")})
pv = _req("GET", "/external/pending/cb-post")
mine = [t for t in (pv.get("tasks") or []) if t["id"] == d]
T("view 带 nonce", bool(mine) and len(mine[0].get("nonce", "")) == 8)
nonce = mine[0]["nonce"] if mine else ""
cb = _req("POST", "/external/callback/cb-post",
          {"done": True, "task_id": d, "ts": time.time(), "nonce": nonce})
T("未领取回执被拒（Cora N6）", "未领取" in str(cb.get("error", "")))
_req("POST", "/external/claim/cb-post", {"task_id": d})
cb2 = _req("POST", "/external/callback/cb-post",
           {"done": True, "task_id": d, "ts": time.time(), "nonce": "deadbeef"})
T("错 nonce 被拒（Lyra②）", "nonce" in str(cb2.get("error", "")))
cb3 = _req("POST", "/external/callback/cb-post",
           {"done": True, "task_id": d, "ts": time.time(), "nonce": nonce})
T("claim+对 nonce 收", cb3.get("ok") is True)

# ── D14 guard_unlock 端点解永久锁（唯一出口必须真能用）──
import asyncio
from office.routers.misc import api_guard_unlock
g5 = ConfirmGateC1()
g5._guard_lock["perm"] = (time.time(), float("inf"))
g5._guard_freeze_n["perm"] = 3
r_u = asyncio.run(api_guard_unlock({"thread_id": "perm"}))
T("D14 端点解永久锁", r_u["ok"] and "perm" not in g5._guard_lock)
T("D14 解后不再冻结", g5._frozen("perm") is False)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
