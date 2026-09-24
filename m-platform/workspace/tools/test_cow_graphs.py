# -*- coding: utf-8 -*-
"""cow_graphs 部门图工厂回归测（09-15 盲区补测一期）。

mock 边界（零活体声明）：
- _role_model 顶替 → 离线 ChatOpenAI 占位对象（不读真实 settings、不触 providers 网络面）
- agent_multimodel 整模块顶替 → backend/门件/知识库工具全为哨兵（不连沙箱服务）
- deepagents create_deep_agent / langgraph 编译 / SubGate 本体：真件（这是被测装配链本身）
- 配置缓存测：_DEPT_CONFIG 重定向 tmp 文件，测后恢复全局态
断言面：_build_dept_graph 编译成功、SubGate 主管/牛马双层在列、影子编制封印、
invalidate_dept_cache 后重建（零重启语义）、占位图与构建失败回落、_inner_config 剥键、
assert_dept_gates 子层正反接线断言（09-16 fix4：缺 SubGate 炸 / 错装 ConfirmGateC1 炸）。
"""
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from langchain_openai import ChatOpenAI  # noqa: E402

import cow_graphs as cg  # noqa: E402
from mia_agent.confirm_gate_c1 import SubGate  # noqa: E402

ok, fail = 0, []
CELLS = []


def T(name, cond):
    global ok
    if cond:
        ok += 1
        CELLS.append(name)
    else:
        fail.append(name)
        print("  FAIL", name)


def fake_model(role, **kw):
    return ChatOpenAI(model="mock-offline", api_key="EMPTY",
                      base_url="https://mock.invalid")


def KB_SENTINEL(*a, **k):
    """知识库检索（测试哨兵）。"""
    return "kb"


def fake_am():
    m = types.ModuleType("agent_multimodel")

    class _Backend:
        def __init__(self, root_dir=None):
            self.root_dir = root_dir

    m.SandboxedShellBackend = _Backend
    m.ConfirmGateMiddleware = type("ConfirmGateMiddleware", (), {})
    m.search_knowledge_base = KB_SENTINEL
    return m


def spec_get(spec, key):
    return spec[key] if isinstance(spec, dict) else getattr(spec, key)


DEPT = {"slot": "dept_8", "name": "测试部",
        "supervisor": {"role": "boss"},
        "workers": [{"name": "coder", "role": "coder", "desc": "码农"}]}

AM = fake_am()

# ── 1. _build_dept_graph 真编译成功 ──
with patch.object(cg, "_role_model", fake_model), patch.dict(sys.modules, {"agent_multimodel": AM}):
    try:
        g = cg._build_dept_graph(DEPT, "dept_8")
        compiled = g is not None and hasattr(g, "invoke")
    except Exception as e:
        compiled = False
        print("  [build 真编译失败明细]", type(e).__name__, str(e)[:200])
T("1 _build_dept_graph 编译成功返回可 invoke 图", compiled)

# ── 2. 装配参数捕获：SubGate 在列 + 影子编制封印 + 工具池 ──
CAP = {}


def spy_create(**kw):
    CAP.update(kw)
    return "SPY_GRAPH"


DEPT2 = json.loads(json.dumps(DEPT))
DEPT2["workers"] = [
    {"name": "researcher", "role": "researcher"},                    # 默认池：kb+web
    {"name": "guard", "tools": ["search_knowledge_base", "bogus"]},  # 池外名字被滤
    {"name": "runner", "tools": ["execute", "ls"]},                  # 官方自动栈不算池外
    {"name": "skilled", "skills": ["no_such_card"]},                 # 缺卡：出声不炸
]
with patch.object(cg, "_role_model", fake_model), \
     patch.object(cg, "create_deep_agent", spy_create), \
     patch.dict(sys.modules, {"agent_multimodel": AM}):
    g2 = cg._build_dept_graph(DEPT2, "dept_8")
T("2 装配走 create_deep_agent（spy 捕获）", g2 == "SPY_GRAPH")
mws = CAP.get("middleware") or []
T("2 主管层 SubGate 在列", any(isinstance(m, SubGate) for m in mws))
T("2 主管层 RunConfigMiddleware 在列",
  any(type(m).__name__ == "RunConfigMiddleware" for m in mws))
subs = CAP.get("subagents") or []
names = [spec_get(s, "name") for s in subs]
T("2 牛马逐个入列", set(["researcher", "guard", "runner", "skilled"]) <= set(names))
T("2 影子编制 general-purpose 封印在列", "general-purpose" in names)
gp = next(s for s in subs if spec_get(s, "name") == "general-purpose")
gp_runnable = spec_get(gp, "runnable")
out = gp_runnable.invoke({"messages": [{"role": "user", "content": "派活"}]})
T("2 gp 封印图返回退役军规",
  "退役" in str(out["messages"][-1].get("content") if isinstance(out["messages"][-1], dict)
                else out["messages"][-1].content))
wsubs = {spec_get(s, "name"): s for s in subs if spec_get(s, "name") != "general-purpose"}
T("2 牛马层 SubGate 各挂各的（R66 官方规则）",
  all(any(isinstance(m, SubGate) for m in (spec_get(s, "middleware") or []))
      for s in wsubs.values()))
T("2 researcher 默认池=知识库+联网", len(spec_get(wsubs["researcher"], "tools") or []) == 2)
T("2 池外工具被滤不入库", len(spec_get(wsubs["guard"], "tools") or []) == 1
  and (spec_get(wsubs["guard"], "tools") or [None])[0] is KB_SENTINEL)
T("2 官方自动栈工具名不发放（execute/ls 静默跳过）",
  spec_get(wsubs["runner"], "tools") == [])
sk = spec_get(wsubs["skilled"], "system_prompt")
T("2 缺技能卡仍出厂（提示词在）", isinstance(sk, str) and sk)

# ── 3. 工厂缓存与 invalidate（零重启语义，build 顶替为哨兵计数） ──
tmp = Path(tempfile.mkdtemp(prefix="zcow_"))
cfgf = tmp / "departments_config.json"
cfgf.write_text(json.dumps({"departments": [DEPT]}, ensure_ascii=False), encoding="utf-8")

_real_cache, _real_mtime, _real_cfg = dict(cg._dept_cache), cg._cfg_mtime, cg._DEPT_CONFIG
builds = {"n": 0}


def counting_build(dept, slot):
    builds["n"] += 1
    return f"G{builds['n']}"


try:
    cg._dept_cache.clear()
    with patch.object(cg, "_DEPT_CONFIG", cfgf), \
         patch.object(cg, "_build_dept_graph", counting_build):
        first = cg._get_dept_graph("dept_8")
        second = cg._get_dept_graph("dept_8")
        T("3 同配置二次取图吃缓存（构建次数=1）", first is second and builds["n"] == 1)
        cg.invalidate_dept_cache()
        T("3 invalidate 清空整表", cg._dept_cache == {})
        third = cg._get_dept_graph("dept_8")
        T("3 invalidate 后重建=新图", third != first and builds["n"] == 2)
        # 改配置（mtime 变）→ 自动重建，无需 invalidate
        import os as _os
        _os.utime(cfgf, (cfgf.stat().st_atime, cfgf.stat().st_mtime + 10))
        fourth = cg._get_dept_graph("dept_8")
        T("3 配置文件 mtime 变更自动重建（人事权零重启）",
          fourth != third and builds["n"] == 3)
        # 未配置槽位 → 占位图
        ph = cg._get_dept_graph("dept_7")
        r = ph.invoke({"messages": [{"role": "user", "content": "hi"}]})
        msg = r["messages"][-1]
        txt = msg.get("content") if isinstance(msg, dict) else msg.content
        T("3 未配置槽位回落占位图", "未配置" in str(txt) and builds["n"] == 3)
finally:
    cg._dept_cache.clear()
    cg._dept_cache.update(_real_cache)
    cg._cfg_mtime = _real_mtime
    cg._DEPT_CONFIG = _real_cfg

# ── 4. 构建失败 → 占位图顶住（派活不炸服务器） ──
try:
    cg._dept_cache.clear()
    with patch.object(cg, "_DEPT_CONFIG", cfgf), \
         patch.object(cg, "_build_dept_graph",
                      lambda d, s: (_ for _ in ()).throw(RuntimeError("mock 构建炸"))):
        fb = cg._get_dept_graph("dept_8")
        r = fb.invoke({"messages": [{"role": "user", "content": "hi"}]})
        msg = r["messages"][-1]
        txt = msg.get("content") if isinstance(msg, dict) else msg.content
        T("4 构建失败回落占位图（可 invoke）", "未配置" in str(txt) or "配置" in str(txt))
finally:
    cg._dept_cache.clear()
    cg._dept_cache.update(_real_cache)
    cg._cfg_mtime = _real_mtime

# ── 5. _placeholder 独立测 + _inner_config 剥键（R80 钉） ──
p = cg._placeholder("dept_3")
r = p.invoke({"messages": [{"role": "user", "content": "x"}]})
T("5 占位图编译为可 invoke 图", hasattr(p, "invoke"))
T("5 占位图文案带槽位名", "dept_3" in str(r["messages"][-1]))
c = cg._inner_config({"configurable": {"thread_id": "t1", "user_id": "u",
                                       "__pregel_checkpointer": object(),
                                       "checkpoint_id": "c9"},
                      "recursion_limit": 50})
T("5 _inner_config 剥注入 saver 与 checkpoint_id",
  "__pregel_checkpointer" not in c["configurable"]
  and "checkpoint_id" not in c["configurable"])
T("5 thread_id/user_id 保留（子图 _tid 依赖）",
  c["configurable"].get("thread_id") == "t1" and c["configurable"].get("user_id") == "u")
T("5 None 入参不炸", isinstance(cg._inner_config(None), dict))

# ── 6. assert_dept_gates 子层接线断言（09-16 fix4：兑现"子层不验"欠账，fail-closed） ──
# 按类名比对（同 assert_gate_order 惯用法），故反向错装件用同名哨兵类即可命中判据。
_FakeMainGate = type("ConfirmGateC1", (), {})


def _raises(coro_list):
    try:
        cg.assert_dept_gates(coro_list)
        return False
    except ValueError:
        return True


T("6 正装（含 SubGate 无主门）过", not _raises([SubGate(dept="测试部/coder")]))
T("6 塞 ConfirmGateC1 反向错装→炸（主门混进部门图=口头门死锁形状）",
  _raises([SubGate(dept="x"), _FakeMainGate()]))
T("6 缺 SubGate→炸（fail-closed 不许静默出厂）",
  _raises([type("RunConfigMiddleware", (), {})()]))

# ── 7. 装配链真调 assert_dept_gates 钉子（09-16 fix5 工兵自报 spy 缺口）──
# 前 6 组只验 assert_dept_gates 本体判据；若把 _build_dept_graph 里的调用点删了，本体测照样全绿=漏网。
# 此格 monkeypatch 计数版 assert_dept_gates、真跑 _build_dept_graph，钉死"装配链确实调了它"。
_gate_calls = {"n": 0}
_real_adg = cg.assert_dept_gates


def _spy_adg(middlewares):
    _gate_calls["n"] += 1
    return _real_adg(middlewares)  # 透传真验：不改 fail-closed 语义，只数调用次数


with patch.object(cg, "_role_model", fake_model), \
     patch.object(cg, "create_deep_agent", lambda **kw: "SPY7"), \
     patch.object(cg, "assert_dept_gates", _spy_adg), \
     patch.dict(sys.modules, {"agent_multimodel": AM}):
    cg._build_dept_graph(DEPT, "dept_8")
T("7 _build_dept_graph 装配链真调 assert_dept_gates（≥1 次，删调用点此格即红）", _gate_calls["n"] >= 1)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
print("格单：" + " | ".join(f"{i+1}. {c}" for i, c in enumerate(CELLS)))
sys.exit(1 if fail else 0)
