# -*- coding: utf-8 -*-
"""D2 压力降档测试（plan-d2-pressure-v1，09-15 爸爸批 N=3）——机械可判格：
A：3 连败触发降档+落账字段全（tid/streak/fails≤3条各≤80字）+钉后读档=strict；
B：中途成功清零（再攒满才触发）；
C：已在 strict/plan 不重复降（无钉、落账照记、告知文案如实"未再降档"）；
D：批准卡放行解除（reject 不解除；approve 清零+撤钉+读档回真源+撤钉落账可查）；
E：未达阈值不降（2 连败无钉无账）；
F：临时钉不污染 settings 真源（真实 _level 走假 load_settings：真源纹丝不动、
   save_section 零调用、设置文件字节级快照不变）；
G：一切 error 态都计 1（崩溃/拒信/工具 error 三种形态凑满触发；崩溃必 re-raise）；
H：降档告知只附"下一次"（拒信面消费即清；卡面同款共一只旗）；
I：崩溃×触发 交集格（hy4 十二轮 P-C 补测：_level 二次读抛时真异常仍原样冒出、计数照落；
   十三轮卫生批①③补：readfail 照落账有断言、兜底告知挂旗且不报档位）。
十六轮修复批新增格（hy4 裁决 A-E 五组）：B=件一回归（read_level=生效档）；
C=件四折中案（钉下再触发账带 pin:1/常态帧零膨胀）；M5=死信触发面扩（清锁抛也
落死信，ok=True 无条件，部分成功现场保全）；M6=死信缺省新址断言（runtime/）；
D=件三护栏非空输入帧（三端点 error 键绝迹扩语义路径）。
d2v03fix3 新增（09-15 夜，规格=若若261 P1+Cora263 五件）：Q=三清扩面（reset 后
freeze_n/mid/hits 已清、deny 刻意保留）；R=竞态格（双线程并发 _note_fail 不丢数）；
P 组=上沿账（真落钉/残余帧皆 pin_set:1+pin_id，ttl/批准/reset 三路账统一带 pin_id——
"一颗钉的一生"单查询）；J/C/M 组等手工钉一律改 (ts,pin_id) 元组形（_pin_alive 解包
跟改）；件八补三漏=M 组落账侧 budget/budget_detail、M4/M5 死信行 ev/budget_detail。
需 langchain：容器内跑（test_c1_hook 同法），宿主用 D:\\m\\workspace\\.venv。"""
import os, sys, json, time, tempfile
sys.path.insert(0, os.environ.get("MIA_SRC", r"D:\m\workspace"))
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
from langchain_core.messages import ToolMessage
import approvals as ap  # noqa: E402
import settings_mgr  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402

tmp = tempfile.mkdtemp(); ap._AUDIT_PATH = os.path.join(tmp, "a.jsonl")
ConfirmGateC1._PRESSURE_PIN.clear()  # 类级钉从干净账开跑（跨格不串）
ConfirmGateC1._fail_streak.clear()   # D2 四件②后 streak/notice 也是类级，同规清账
ConfirmGateC1._pressure_notice.clear()

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

def _recs(ev):
    return [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
            if f'"{ev}"' in l]

class R:
    """最小 ToolCallRequest 替身（wrap 只读 request.tool_call）。"""
    def __init__(self, name, args, rid="r1"):
        self.tool_call = {"name": name, "args": args, "id": rid}

def err_handler(request):
    return ToolMessage(content="boom", tool_call_id="r1", status="error")

def ok_handler(request):
    return ToolMessage(content="fine", tool_call_id="r1", status="success")

def boom_handler(request):
    raise ValueError("kaboom")

# 秘密参数样本：账里绝不允许出现原文（脱敏口径同 guard_high——只落 fp 不落 args）
_SECRET = "notes/super_secret_marker_d2.txt"

# ── A：3 连败触发降档+落账字段全 ──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    ga = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2a")):
        r = lambda i: R("write_file", {"file_path": _SECRET, "content": "x"}, f"a{i}")
        ga.wrap_tool_call(r("a1"), err_handler)
        ga.wrap_tool_call(r("a2"), err_handler)
        T("A 前提：两连败未触发（无钉无账）",
          "d2a" not in ConfirmGateC1._PRESSURE_PIN and ga._fail_streak["d2a"]["n"] == 2)
        ga.wrap_tool_call(r("a3"), err_handler)
        T("A 三连败钉入 _PRESSURE_PIN", "d2a" in ConfirmGateC1._PRESSURE_PIN)
        T("A 钉后读档=strict（真源仍 auto_edit，见 F 格另证）",
          ConfirmGateC1.read_level() == "strict")
        T("A 路由随之变 ask（write_file 在钉住线程需请示）",
          ga._route("write_file", {"file_path": "notes/x.md", "content": "y"}) == "ask")
        rec = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2a"]
        T("A 落账 desk_pressure_downgrade 一条且 tid/streak 对",
          len(rec) == 1 and rec[0].get("streak") == 3)
        fl = rec[0].get("fails") or [] if rec else []
        T("A fails=最近3条各≤80字且带 fp 指纹",
          len(fl) == 3 and all(len(s) <= 80 and "fp=" in s for s in fl))
        T("A 脱敏：args 原文不进账（同 guard_high 口径）",
          _SECRET not in json.dumps(rec, ensure_ascii=False))
        T("A 告知旗已挂（下一次拒信/卡面附一行）",
          "d2a" in ga._pressure_notice and "复核方向" in ga._pressure_notice["d2a"])

# ── B：中途成功清零，再攒满才触发 ──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gb = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2b")):
        r = lambda i: R("write_file", {"file_path": "notes/b.md", "content": "x"}, f"b{i}")
        for i in ("b1", "b2"):
            gb.wrap_tool_call(r(i), err_handler)
        gb.wrap_tool_call(r("b3"), ok_handler)  # 成功一刀清
        T("B 成功调用清零计数", "d2b" not in gb._fail_streak)
        for i in ("b4", "b5"):
            gb.wrap_tool_call(r(i), err_handler)
        T("B 清零后两连败不触发",
          "d2b" not in ConfirmGateC1._PRESSURE_PIN
          and not [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2b"])
        gb.wrap_tool_call(r("b6"), err_handler)
        recb = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2b"]
        T("B 再攒满 3 才触发（streak=3 不是 5）",
          "d2b" in ConfirmGateC1._PRESSURE_PIN and len(recb) == 1
          and recb[0]["streak"] == 3)

# ── C：已在 strict/plan 不重复降（降档要素跳过，落账+告知照旧）──
for lvl in ("strict", "plan"):
    with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda l=lvl: l)):
        gc = ConfirmGateC1(sub_mode=False)
        tid = "d2c-" + lvl
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda t=tid: t)):
            msgs = [gc.wrap_tool_call(R("execute", {"command": "ls"}, f"c{i}"), err_handler)
                    for i in range(3)]
            T(f"C {lvl} 档 3 连败不加钉（不重复降）", tid not in ConfirmGateC1._PRESSURE_PIN)
            recc = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == tid]
            T(f"C {lvl} 档落账照记（压力可见性不因档而异）",
              len(recc) == 1 and recc[0]["streak"] == 3)
            # 告知落点与档形相关：plan 第 3 败本身即拒信=当场随附（attach 在计数后）；
            # strict 第 3 败是工具 error 回复=旗挂待下一次拒信/卡面。两处任一见文案即对。
            _seen = (gc._pressure_notice.get(tid)
                     or (msgs[-1].content if msgs[-1] is not None else ""))
            T(f"C {lvl} 档告知文案如实「未再降档」", "未再降档" in _seen)

# ── D：批准卡放行解除；reject 不放行不解除 ──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gd = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2d")):
        for i in range(3):
            gd.wrap_tool_call(R("write_file", {"file_path": "notes/d.md"}, f"d{i}"),
                              err_handler)
        T("D 前提：已钉已连败", "d2d" in ConfirmGateC1._PRESSURE_PIN
          and gd._fail_streak.get("d2d", {}).get("n") == 3)
        tc = {"name": "write_file", "args": {"file_path": "notes/d.md"}, "id": "dz"}
        try:
            gd._process_decision({"type": "reject", "message": "停"},
                                 tc, {"allowed_decisions": ["approve", "edit", "reject"]})
        except Exception:
            pass  # 官方件对 reject 的返回构造不属本格，只钉解除语义
        T("D reject 不算放行（钉与计数原样）",
          "d2d" in ConfirmGateC1._PRESSURE_PIN and "d2d" in gd._fail_streak)
        try:
            gd._process_decision({"type": "approve"}, tc,
                                 {"allowed_decisions": ["approve", "edit", "reject"]})
        except Exception:
            pass
        T("D approve 撤钉", "d2d" not in ConfirmGateC1._PRESSURE_PIN)
        T("D approve 清零计数", "d2d" not in gd._fail_streak)
        T("D approve 后读档回真源 auto_edit",
          ConfirmGateC1.read_level() == "auto_edit")
        # hy4 十三轮卫生批②：④ 的初衷是"钉有账、撤无声=半本账"——release 账必须在
        # temp 账里可查（键名 desk_pressure_release + tid），账名写坏/落点走错模块在此报警。
        recr = [x for x in _recs("desk_pressure_release") if x.get("tid") == "d2d"]
        T("D 撤钉照落账 desk_pressure_release（键名+tid 在 temp 账可查且仅一条）",
          len(recr) == 1)
        # hy4 十二轮必改②：原末条 "d2fresh" not in _fail_streak 是空断言（该键全程
        # 未被碰过、approve 后又已清成 {}，对任何未出现 key 恒真）。换真断言：同实例
        # 把 _tid 切到新线程 → read_level 真切走新 tid 的判定路径 → 断言回真源且无 streak 键。
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2fresh")):
            T("D 新线程自然重置（同实例切新 tid：read_level 回真源 auto_edit 且无 streak 键）",
              ConfirmGateC1.read_level() == "auto_edit" and "d2fresh" not in gd._fail_streak)

# ── E：未达阈值不降 ──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    ge = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2e")):
        for i in range(2):
            ge.wrap_tool_call(R("write_file", {"file_path": "notes/e.md"}, f"e{i}"),
                              err_handler)
        T("E 两连败：无钉、无账、计数=2",
          "d2e" not in ConfirmGateC1._PRESSURE_PIN
          and not [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2e"]
          and ge._fail_streak["d2e"]["n"] == 2)

# ── F：临时钉不污染 settings 真源（真实 _level 走假 load_settings，零文件写）──
_saved, _orig_save = [], settings_mgr.save_section  # settings.json 唯一写通道=settings_mgr.save_section
try:
    settings_mgr.save_section = lambda *a, **k: _saved.append(a)
    _p = str(settings_mgr.SETTINGS_PATH)
    _snap = open(_p, "rb").read() if os.path.exists(_p) else b"<absent>"
    _fake = lambda: {"general": {"confirmLevel": "auto_edit"}}  # 无 desk_pressure_n 键=走缺省 3
    with patch.object(settings_mgr, "load_settings", _fake):
        gf = ConfirmGateC1(sub_mode=False)
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2f")):
            T("F 前提：真源经 load_settings 读出 auto_edit",
              ConfirmGateMiddleware._level() == "auto_edit")
            for i in range(3):
                gf.wrap_tool_call(R("write_file", {"file_path": "notes/f.md"}, f"f{i}"),
                                  err_handler)
            T("F 钉后：真源 _level() 纹丝不动",
              ConfirmGateMiddleware._level() == "auto_edit")
            T("F 钉后：读档入口覆盖成 strict", ConfirmGateC1.read_level() == "strict")
    T("F 全程零调 save_section（不写配置）", _saved == [])
    T("F 设置文件字节级快照不变",
      open(_p, "rb").read() == _snap if os.path.exists(_p) else _snap == b"<absent>")
finally:
    settings_mgr.save_section = _orig_save

# ── G：一切 error 态都计 1（崩溃/拒信/工具 error 凑满触发；崩溃必 re-raise）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gg = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2g")):
        raised = False
        try:
            gg.wrap_tool_call(R("execute", {"command": "ls"}, "g1"), boom_handler)
        except ValueError:
            raised = True
        T("G 崩溃计入且原样 re-raise（钩子不吃异常）",
          raised and gg._fail_streak["d2g"]["n"] == 1)
        m = gg.wrap_tool_call(R("write_file", {"file_path": "mia_agent/x.py"}, "g2"),
                              err_handler)  # selflock=门拒信（不该走到 handler）
        T("G guard 拒信计 1", m is not None and gg._fail_streak["d2g"]["n"] == 2)
        gg.wrap_tool_call(R("execute", {"command": "ls"}, "g3"), err_handler)
        recg = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2g"]
        kinds = " ".join((recg[0]["fails"] if recg else []))
        T("G 三形态混合连败在第 3 次触发",
          "d2g" in ConfirmGateC1._PRESSURE_PIN and len(recg) == 1)
        T("G fails 摘要含三种 kind 且崩溃只留异常类名",
          all(k in kinds for k in ("crash", "refuse", "tool_error"))
          and "ValueError" in kinds and "kaboom" not in kinds)
        # 触发后再撞（n>N）不重复落账：同段压力只记一次
        gg.wrap_tool_call(R("execute", {"command": "ls"}, "g4"), err_handler)
        T("G 第 4 次连败不重复触发（fired 旗：同段只触发一次）",
          len([x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2g"]) == 1
          and gg._fail_streak["d2g"]["n"] == 4)

# ── H：降档告知附"下一次"（拒信面+卡面，共一只旗，消费即清）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gh = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2h")):
        for i in range(3):
            gh.wrap_tool_call(R("write_file", {"file_path": "notes/h.md"}, f"h{i}"),
                              err_handler)
        m1 = gh.wrap_tool_call(R("write_file", {"file_path": "mia_agent/x.py"}, "hx"),
                               err_handler)  # selflock 拒信
        T("H 触发后下一次拒信附降档告知一行",
          m1 is not None and "复核方向" in m1.content and "自动降为变更前确认" in m1.content)
        m2 = gh.wrap_tool_call(R("write_file", {"file_path": "mia_agent/x.py"}, "hy"),
                               err_handler)
        T("H 第二次拒信不再重复附（消费即清）",
          m2 is not None and "复核方向" not in m2.content)
        # 卡面通道：再攒一轮连败挂新旗，desc() 首次含、二次不含
        gh._fail_streak["d2h"] = {"n": 2, "recent": []}
        gh.wrap_tool_call(R("write_file", {"file_path": "notes/h.md"}, "hz"), err_handler)
        d = gh._make_desc("write_file")
        s1 = d({"name": "write_file", "args": {}, "id": "k1"}, {"messages": []}, None)
        s2 = d({"name": "write_file", "args": {}, "id": "k2"}, {"messages": []}, None)
        T("H 卡面首次附告知一行、二次不附（与拒信共一只旗）",
          "复核方向" in s1 and "复核方向" not in s2)

# ── I：崩溃×触发 交集格（hy4 十二轮 P-C 补测——唯一危险帧，G 格当年零覆盖处）──
# N=1 让第 1 败即触发 fire；_level 第 2 次调用（第 1 次在 wrap 的 _route 读档）抛
# RuntimeError 模拟设置页重写窗口内 read_level 二次读炸。断言冒出的是 handler 的
# ValueError（计数钩子没把真异常顶成 settings 异常、raise 无条件可达）且 n 仍为 1。
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gi = ConfirmGateC1(sub_mode=False)
    _lvl_calls = {"n": 0}

    def _flaky_level():
        _lvl_calls["n"] += 1
        if _lvl_calls["n"] >= 2:
            raise RuntimeError("settings torn")
        return "auto_edit"

    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2i")), \
         patch.object(ConfirmGateMiddleware, "_level", staticmethod(_flaky_level)), \
         patch.object(ConfirmGateC1, "_pressure_n", staticmethod(lambda: 1)):
        raised = None
        try:
            gi.wrap_tool_call(R("execute", {"command": "ls"}, "i1"), boom_handler)
        except Exception as _e:
            raised = _e
        T("I 崩溃×触发交集：冒出 ValueError 非 RuntimeError 且 n 不变（仍 1）",
          type(raised) is ValueError and gi._fail_streak.get("d2i", {}).get("n") == 1)
        # hy4 十三轮卫生批③（兼验①）："不钉但照落账"不能只活在 stdout——readfail 账
        # （键名+tid 可查）与 downgrade 账（downgraded=False、level=""）都断言上；
        # 兜底告知必须挂旗且不许报任何档位（level="" 却报"已是 strict/计划档"=断言式谎话）。
        rec_ir = [x for x in _recs("desk_pressure_readfail") if x.get("tid") == "d2i"]
        rec_id = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2i"]
        _note_i = gi._pressure_notice.get("d2i") or ""
        T("I readfail 照落账（readfail 一条+downgrade 账 downgraded=False/level=''）"
          "且兜底告知挂旗不报档位（卫生批①③）",
          len(rec_ir) == 1 and len(rec_id) == 1
          and rec_id[0].get("downgraded") is False and rec_id[0].get("level") == ""
          and "复核方向" in _note_i and "strict" not in _note_i
          and "计划档" not in _note_i and "变更前确认" not in _note_i)

# ── J：四件① 钉 TTL（hy4 十二轮 P-A："临时钉"进程内实为永久→TTL 缺省 24h 惰性到期自清）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2j")):
        ConfirmGateC1._PRESSURE_PIN["d2j"] = (time.time() - 3600, "p-d2j")
        T("J TTL 内（1h<24h）钉有效=strict", ConfirmGateC1.read_level() == "strict")
        ConfirmGateC1._PRESSURE_PIN["d2j"] = (time.time() - 86401, "p-d2j")
        T("J 超 TTL（24h+1s）read_level 回真源", ConfirmGateC1.read_level() == "auto_edit")
        T("J 到期钉已惰性自清", "d2j" not in ConfirmGateC1._PRESSURE_PIN)
        rec_j = [x for x in _recs("desk_pressure_release") if x.get("tid") == "d2j"]
        T("J 到期撤钉落账 reason=ttl（撤钉有声，N1 半本账补齐）且带 pin_id（d2v03fix3⑤）",
          len(rec_j) == 1 and rec_j[0].get("reason") == "ttl"
          and rec_j[0].get("pin_id") == "p-d2j")
    with patch.object(settings_mgr, "load_settings", lambda: {"desk_pressure_pin_ttl_s": 60}):
        ConfirmGateC1._PRESSURE_PIN["d2j2"] = (time.time() - 61, "p-d2j2")
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2j2")):
            T("J TTL 听 settings 键（60s 即到期）", ConfirmGateC1.read_level() == "auto_edit")
        ConfirmGateC1._PRESSURE_PIN.pop("d2j2", None)
    with patch.object(settings_mgr, "load_settings", lambda: {"desk_pressure_pin_ttl_s": "坏值"}):
        T("非法 TTL 回落缺省 86400", ConfirmGateC1._pin_ttl() == 86400)

# ── K：四件② 计数上提类级（hy4 十二轮 N2：计数实例级/钉类级不对称→多实例并账）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    k1 = ConfirmGateC1(sub_mode=False)
    k2 = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2k")):
        k1.wrap_tool_call(R("write_file", {"file_path": "notes/k.md"}, "k1"), err_handler)
        k1.wrap_tool_call(R("write_file", {"file_path": "notes/k.md"}, "k2"), err_handler)
        T("K 实例 A 两连败无钉+两只 dict 已同源类级",
          "d2k" not in ConfirmGateC1._PRESSURE_PIN
          and k2._fail_streak is k1._fail_streak and k1._fail_streak["d2k"]["n"] == 2)
        k2.wrap_tool_call(R("write_file", {"file_path": "notes/k.md"}, "k3"), err_handler)
        T("K 实例 B 第三败跨实例触发（A 攒 2+B 攒 1=3，原实例级永不同框）",
          "d2k" in ConfirmGateC1._PRESSURE_PIN)
    ConfirmGateC1._fail_streak.pop("d2k", None)
    ConfirmGateC1._PRESSURE_PIN.pop("d2k", None)
    ConfirmGateC1._pressure_notice.pop("d2k", None)

# ── L：四件③ 子层盲区（hy4 十二轮 §1：SubGate 原直读真源不受钉→统一走 read_level）──
from mia_agent.confirm_gate_c1 import SubGate
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    sg = SubGate(dept="测试部")
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2l")):
        ConfirmGateC1._PRESSURE_PIN["d2l"] = (time.time(), "p-d2l")
        res_l = sg.wrap_tool_call(R("write_file", {"file_path": "notes/l.md"}, "l1"), ok_handler)
        T("L 被钉线程子层同样受钉：write_file 转'子层请示'不直通",
          isinstance(res_l, ToolMessage) and "[子层请示]" in str(res_l.content)
          and "测试部" in str(res_l.content))
        ConfirmGateC1._PRESSURE_PIN.pop("d2l")
        res_l2 = sg.wrap_tool_call(R("write_file", {"file_path": "notes/l.md"}, "l2"), ok_handler)
        T("L 撤钉后子层回真源 auto_edit：write_file 直通（softwrite 设计路径）",
          isinstance(res_l2, ToolMessage) and res_l2.content == "fine")

# ── L2：十四轮 §③ 话术补断言（hy4 十五轮判"建议必补"）──
# 期望语义先钉（hy4 原话）：(a) pinned 帧——真源 patch 成 auto_edit + 手动钉活，
# SubGate.wrap_tool_call 的上报串必须含"非设置真源变更"（读者能分清临时降档与政令变更）；
# (b) 真源 patch 成 strict + 无钉——上报串必须不含该句（"临时降档"只在钉真实生效时
# 成立，真源 strict 报此句=断言式谎话，十三轮卫生批①同规）。
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    sg2 = SubGate(dept="测试部")
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2l2a")):
        ConfirmGateC1._PRESSURE_PIN["d2l2a"] = (time.time(), "p-d2l2")
        res_l2a = sg2.wrap_tool_call(R("write_file", {"file_path": "notes/l2.md"}, "l2a"),
                                     ok_handler)
        T("L2(a) pinned 帧上报串含「非设置真源变更」",
          isinstance(res_l2a, ToolMessage) and "非设置真源变更" in str(res_l2a.content))
        ConfirmGateC1._PRESSURE_PIN.pop("d2l2a")
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2l2b")):
        res_l2b = sg2.wrap_tool_call(R("write_file", {"file_path": "notes/l2.md"}, "l2b"),
                                     ok_handler)
        T("L2(b) 真源 strict+无钉上报串不含「非设置真源变更」",
          isinstance(res_l2b, ToolMessage) and "非设置真源变更" not in str(res_l2b.content))

# ── L3：v0.3 件一 残余帧闭合（档源真源化）──
# 病灶现场复刻：真源在钉存续期内被爸爸改成 strict 且钉未到期——旧消费端推断
# "lvl==strict 且 _pin_alive"会判 pinned=True，上报"临时降档，非设置真源变更"成谎话
# （此刻 strict 正来自真源）。level_and_source 单一判定处下真源高档直接返回
# (level,"true")（钉不参与），pinned 自然 False。L2 两格不动（旧语义仍成立）。
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2l3")):
        ConfirmGateC1._PRESSURE_PIN["d2l3"] = (time.time(), "p-d2l3")  # 手动活钉=残余帧现场
        res_l3 = sg2.wrap_tool_call(R("write_file", {"file_path": "notes/l3.md"}, "l3"),
                                    ok_handler)
        T("L3 残余帧闭合：真源 strict+活钉，上报串不含「非设置真源变更」（件一）",
          isinstance(res_l3, ToolMessage) and "非设置真源变更" not in str(res_l3.content))
        T("L3 单一判定处：真源高档直返 (strict,'true') 且钉原样在位（高档路不触 _pin_alive 惰性账副作用）",
          ConfirmGateC1.level_and_source() == ("strict", "true")
          and "d2l3" in ConfirmGateC1._PRESSURE_PIN)
        ConfirmGateC1._PRESSURE_PIN.pop("d2l3")

# ── B：十六轮 B 组（件一回归断言：read_level=生效档非设置真源，docstring 已钉死）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2b9")):
        ConfirmGateC1._PRESSURE_PIN["d2b9"] = (time.time(), "p-d2b9")
        T("B pin 活时 read_level==strict（生效档被钉抬高），真源 _level() 仍 auto_edit（钉只在读影子里）",
          ConfirmGateC1.read_level() == "strict"
          and ConfirmGateMiddleware._level() == "auto_edit")
        ConfirmGateC1._PRESSURE_PIN.pop("d2b9")

# ── C：十六轮 C 组（件四折中案：downgrade 账仅 src=="pin" 时带 pin:1）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gcs = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2src")):
        T("C 判定处常态帧（真源低无钉）=(auto_edit,'true')——pin:1 触发源之一确认",
          ConfirmGateC1.level_and_source() == ("auto_edit", "true"))
        ConfirmGateC1._PRESSURE_PIN["d2src"] = (time.time(), "p-d2src")
        T("C 判定处钉活帧=(strict,'pin')——pin:1 唯一触发源",
          ConfirmGateC1.level_and_source() == ("strict", "pin"))
        # 钉已在位、连败再攒满二次触发（放行清零后再攒同景）：src="pin"→账带 pin:1
        gcs._fail_streak["d2src"] = {"n": 2, "recent": ["p"], "fired": False}
        gcs.wrap_tool_call(R("write_file", {"file_path": "notes/src.md"}, "src3"),
                           err_handler)
        rec_src = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2src"]
        T("C 钉活再触发帧账带 pin=1（downgraded=False/level=strict 自解释，不逼读账人组合判）"
          "+d2v03fix3④残余帧同带 pin_set:1+同一 pin_id（钉落下无痕闭合）",
          len(rec_src) == 1 and rec_src[0].get("pin") == 1
          and rec_src[0].get("downgraded") is False and rec_src[0].get("level") == "strict"
          and rec_src[0].get("pin_set") == 1 and rec_src[0].get("pin_id") == "p-d2src")
        ConfirmGateC1._PRESSURE_PIN.pop("d2src")
        gcs._fail_streak.pop("d2src", None)
        gcs._pressure_notice.pop("d2src", None)
        rec_a0 = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2a"]
        T("C 常态新触发帧（A 格账）不带 pin 键（常态零膨胀，旧账形向后兼容）",
          len(rec_a0) == 1 and "pin" not in rec_a0[0])

# ── M：四件④ 三锁齐清出口（hy4 十二轮 P-B：冻结+超预算+压力钉叠加死锁→reset_thread）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gm = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2m")):
        gm._guard_lock["d2m"] = (time.time(), 60)
        gm._guard_streak["d2m"] = [time.time()]
        gm._frozen_hold["d2m"] = {"t9"}
        gm._over_budget = {"d2m": {"t8"}}
        ConfirmGateC1._PRESSURE_PIN["d2m"] = (time.time(), "p-d2m")
        gm._fail_streak["d2m"] = {"n": 3, "recent": ["x"], "fired": True}
        r_m = ConfirmGateC1.reset_thread("d2m")
        T("M 三锁齐清：返回值三计数对且六本账全空",
          r_m.get("ok") and r_m.get("freeze") == 1 and r_m.get("budget") == 1
          and r_m.get("budget_detail") == {"over_budget": 1, "abs_blocked": 0}
          and r_m.get("pressure") == 1
          and "d2m" not in gm._guard_lock and "d2m" not in gm._guard_streak
          and "d2m" not in gm._frozen_hold and "d2m" not in gm._over_budget
          and "d2m" not in ConfirmGateC1._PRESSURE_PIN
          and "d2m" not in gm._fail_streak)
        rec_m = [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m"]
        T("M 重置落账 desk_state_reset（by=admin+三锁计数，P-B 明令）；账侧补断言"
          "budget/budget_detail（件八/若若①）+ pin_id（件五 reset 路）",
          len(rec_m) == 1 and rec_m[0].get("by") == "admin"
          and rec_m[0].get("freeze") == 1 and rec_m[0].get("pressure") == 1
          and rec_m[0].get("budget") == 1
          and rec_m[0].get("budget_detail") == {"over_budget": 1, "abs_blocked": 0}
          and rec_m[0].get("pin_id") == "p-d2m")
        T("M 空 tid 拒绝（? 桶不连坐）", ConfirmGateC1.reset_thread("").get("ok") is False)
        T("M 重置后读档回真源", ConfirmGateC1.read_level() == "auto_edit")

# ── M2/M3：十四轮 §⑤ 两表同中（budget=命中数之和）+ 落账失败=三锁原样未清 ──
# 顺序决策（本单主项）：先算 → 先落账 → 落账成功才清锁。落账抛时锁根本没清，
# 出口语义="本次重置未完成、请重试/人工"，绝不允许"清了锁没账"的无痕态。
gm._over_budget = {"d2m2": {"t8"}}
gm._abs_blocked["d2m2"] = {"t7"}
ConfirmGateC1._PRESSURE_PIN["d2m2"] = (time.time(), "p-d2m2")
r_m2 = ConfirmGateC1.reset_thread("d2m2")
T("M2 两表同中：budget==2（命中数之和，单实例最多 2）且 budget_detail 分列 1/1",
  r_m2.get("ok") and r_m2.get("budget") == 2
  and r_m2.get("budget_detail") == {"over_budget": 1, "abs_blocked": 1}
  and r_m2.get("freeze") == 0 and r_m2.get("pressure") == 1)
T("M2 两表键都真被清掉", "d2m2" not in gm._over_budget and "d2m2" not in gm._abs_blocked)
rec_m2 = [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m2"]
T("M2 落账带 budget_detail 明细（账与返回值同口径）",
  len(rec_m2) == 1 and rec_m2[0].get("budget") == 2
  and rec_m2[0].get("budget_detail") == {"over_budget": 1, "abs_blocked": 1})

gm._guard_lock["d2m3"] = (time.time(), 60)
gm._guard_streak["d2m3"] = [time.time()]
gm._frozen_hold["d2m3"] = {"t5"}
gm._over_budget = {"d2m3": {"t6"}}
ConfirmGateC1._PRESSURE_PIN["d2m3"] = (time.time(), "p-d2m3")
with patch.object(ap, "_audit", side_effect=RuntimeError("audit down")):
    r_m3 = ConfirmGateC1.reset_thread("d2m3")
T("M3 落账失败→ok=False 且 reason 明说三锁未清（禁静默，不假装成功）",
  r_m3.get("ok") is False and "三锁未清" in str(r_m3.get("reason", "")))
T("M3 落账失败时三锁原样未动：钉在、冻结锁在、退避计数在、超预算登记在",
  "d2m3" in ConfirmGateC1._PRESSURE_PIN and "d2m3" in gm._guard_lock
  and "d2m3" in gm._guard_streak and "d2m3" in gm._over_budget
  and "d2m3" in gm._frozen_hold)
T("M3 落账失败不留 desk_state_reset 假账（无痕态=零条）",
  not [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m3"])
r_m3b = ConfirmGateC1.reset_thread("d2m3")  # 账恢复后重试即成（出口语义=请重试）
T("M3 重试即成：ok=True 且三锁齐清",
  r_m3b.get("ok") and r_m3b.get("freeze") == 1 and r_m3b.get("budget") == 1
  and "d2m3" not in gm._guard_lock and "d2m3" not in gm._over_budget
  and "d2m3" not in ConfirmGateC1._PRESSURE_PIN)

# ── M4：v0.3 件二 force 审计链（治"解锁通道随审计链挂死"）──
# 病灶：M3 序下 _audit 挂=三锁永远解不开。force=True 倒序：先三清（出口优先）再试
# 落 desk_state_reset（带 forced:true）；落账仍抛 → print 出声 + 死信文件一行
# （含 tid/计数/异常名）→ 返回 ok:True/forced/deadletter。死信路径改道 temp
# （_DEADLETTER_PATH 类属性直赋值即换向，同 ap._AUDIT_PATH 手法），断言后清场。
_dl = os.path.join(tmp, "bypass_deadletter.jsonl")
ConfirmGateC1._DEADLETTER_PATH = _dl
gm._guard_lock["d2m4"] = (time.time(), 60)
gm._guard_streak["d2m4"] = [time.time()]
gm._frozen_hold["d2m4"] = {"t4"}
gm._over_budget = {"d2m4": {"t9"}}
ConfirmGateC1._PRESSURE_PIN["d2m4"] = (time.time(), "p-d2m4")
gm._fail_streak["d2m4"] = {"n": 3, "recent": ["x"], "fired": True}
with patch.object(ap, "_audit", side_effect=RuntimeError("audit down")):
    r_m4 = ConfirmGateC1.reset_thread("d2m4", force=True)
T("M4 force=True 落账仍抛：三锁齐清+返回 forced/audit=deadletter（出口优先，件二）",
  r_m4.get("ok") and r_m4.get("forced") and r_m4.get("audit") == "deadletter"
  and "d2m4" not in gm._guard_lock and "d2m4" not in gm._guard_streak
  and "d2m4" not in gm._frozen_hold and "d2m4" not in gm._over_budget
  and "d2m4" not in ConfirmGateC1._PRESSURE_PIN and "d2m4" not in gm._fail_streak)
try:
    _dl_txt = open(_dl, encoding="utf-8").read()
except Exception:
    _dl_txt = ""
_dl_recs = [json.loads(l) for l in _dl_txt.splitlines() if l.strip()]
T("M4 死信文件恰一行且含 tid/计数/异常名（账降尽力+死信兜底，不丢现场）"
  "且十六轮字段补齐：ts/stage=audit/cleared=True/forced_reset=True"
  "+件八补 ev 与 budget_detail 字段断言",
  len(_dl_recs) == 1 and _dl_recs[0].get("tid") == "d2m4"
  and _dl_recs[0].get("freeze") == 1 and _dl_recs[0].get("budget") == 1
  and _dl_recs[0].get("pressure") == 1 and _dl_recs[0].get("err") == "RuntimeError"
  and _dl_recs[0].get("ts") and _dl_recs[0].get("stage") == "audit"
  and _dl_recs[0].get("cleared") is True and _dl_recs[0].get("forced_reset") is True
  and _dl_recs[0].get("ev") == "bypass_deadletter"
  and _dl_recs[0].get("budget_detail") == {"over_budget": 1, "abs_blocked": 0})
T("M4 force=True 落账抛时不留 desk_state_reset 假账（真账搬家死信，主账仍零条）",
  not [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m4"])
ConfirmGateC1._DEADLETTER_PATH = None  # 复位惰性（temp 目录里的死信随 tmp 自灭，不删档）

# force=False 对照格：同一"落账抛"现场，正序必须纹丝不动（M3 原断言不动，此处再立一证）
gm._guard_lock["d2m4f"] = (time.time(), 60)
gm._over_budget["d2m4f"] = {"t5"}
ConfirmGateC1._PRESSURE_PIN["d2m4f"] = (time.time(), "p-d2m4f")
with patch.object(ap, "_audit", side_effect=RuntimeError("audit down")):
    r_m4f = ConfirmGateC1.reset_thread("d2m4f", force=False)
T("M4 force=False 对照：正序不变（落账抛→ok=False+三锁原样未动，M3 语义零回归）",
  r_m4f.get("ok") is False and r_m4f.get("forced") is None
  and "d2m4f" in gm._guard_lock and "d2m4f" in gm._over_budget
  and "d2m4f" in ConfirmGateC1._PRESSURE_PIN)
gm._guard_lock.pop("d2m4f", None)
gm._over_budget.pop("d2m4f", None)
ConfirmGateC1._PRESSURE_PIN.pop("d2m4f", None)
# force 帧的账路正常态：设计"成功带 forced:true"——端点侧 force 判据（r.get("forced")）契约在此钉
ConfirmGateC1._PRESSURE_PIN["d2m4ok"] = (time.time(), "p-d2m4ok")
r_m4ok = ConfirmGateC1.reset_thread("d2m4ok", force=True)
rec_m4ok = [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m4ok"]
T("M4 force 帧账路正常：返回 forced+计数、desk_state_reset 真账注 forced=true、不触死信",
  r_m4ok.get("ok") and r_m4ok.get("forced") and r_m4ok.get("freeze") == 0
  and r_m4ok.get("pressure") == 1 and "audit" not in r_m4ok
  and "d2m4ok" not in ConfirmGateC1._PRESSURE_PIN
  and len(rec_m4ok) == 1 and rec_m4ok[0].get("forced") is True)

# ── M5/M6：十六轮 A 组三改（触发面扩：清锁抛也落死信；ok=True 无条件；新址断言）──
# 清锁注入抛（_clear_three_locks 打桩）——旧实现此帧=裸异常直冒给端点（force 出口
# 反而比正序更脆）；新实现转死信+ok=True。死信仍 tempfile 改道，不污染真 mia_home。
_dl5 = os.path.join(tmp, "bypass_deadletter_m5.jsonl")
ConfirmGateC1._DEADLETTER_PATH = _dl5
gm._guard_lock["d2m5"] = (time.time(), 60)
gm._over_budget["d2m5"] = {"t3"}
ConfirmGateC1._PRESSURE_PIN["d2m5"] = (time.time(), "p-d2m5")
with patch.object(ConfirmGateC1, "_clear_three_locks", side_effect=RuntimeError("clear torn")):
    r_m5 = ConfirmGateC1.reset_thread("d2m5", force=True)
T("M5 清锁抛：不裸冒、ok=True 无条件+forced/audit=deadletter 返回帧（出口优先不反杀）",
  r_m5.get("ok") and r_m5.get("forced") and r_m5.get("audit") == "deadletter")
try:
    _dl5_recs = [json.loads(l) for l in open(_dl5, encoding="utf-8").read().splitlines()
                 if l.strip()]
except Exception:
    _dl5_recs = []
T("M5 死信行=部分成功现场保全：stage=clear_locks/cleared=False/forced_reset=True/ts"
  "/清前三锁计数（peek 在清之前，freeze=1/budget=1/pressure=1）/异常类名"
  "+件八补 ev 与 budget_detail 字段断言",
  len(_dl5_recs) == 1 and _dl5_recs[0].get("stage") == "clear_locks"
  and _dl5_recs[0].get("cleared") is False and _dl5_recs[0].get("forced_reset") is True
  and _dl5_recs[0].get("ts") and _dl5_recs[0].get("freeze") == 1
  and _dl5_recs[0].get("budget") == 1 and _dl5_recs[0].get("pressure") == 1
  and _dl5_recs[0].get("err") == "RuntimeError"
  and _dl5_recs[0].get("ev") == "bypass_deadletter"
  and _dl5_recs[0].get("budget_detail") == {"over_budget": 1, "abs_blocked": 0})
T("M5 清锁抛不触账路：desk_state_reset 零条（账未落、锁未清全，读死信者自行接管）",
  not [x for x in _recs("desk_state_reset") if x.get("tid") == "d2m5"])
for _d in (gm._guard_lock, gm._over_budget, ConfirmGateC1._PRESSURE_PIN):
    _d.pop("d2m5", None)  # 注入态下清锁没成功，键留在现场——本性格自行清场不外溢
ConfirmGateC1._DEADLETTER_PATH = None  # 复位惰性（temp 死信随 tmp 自灭）
T("M6 死信缺省新址=mia_home/runtime/（与主账 notes/ 分离——同目录=兜底同故障域+备份回滚风险；"
  "字符串断言不真写生产目录，目录首写自建逻辑在 dump 内 makedirs）",
  ConfirmGateC1._deadletter_default().replace("\\", "/").endswith(
      "mia_home/runtime/bypass_deadletter.jsonl")
  and "/notes/" not in ConfirmGateC1._deadletter_default().replace("\\", "/"))

# ── 阈值可调（settings 缺省 3；键存在则听键——不写配置文件，用假 load 验证读侧）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    with patch.object(settings_mgr, "load_settings", lambda: {"desk_pressure_n": 2}):
        gk2 = ConfirmGateC1(sub_mode=False)
        T("N 读 settings.desk_pressure_n=2", gk2._pressure_n() == 2)
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2n")):
            for i in range(2):
                gk2.wrap_tool_call(R("write_file", {"file_path": "notes/n.md"}, f"n{i}"),
                                   err_handler)
            T("N=2 时两连败即触发", "d2n" in ConfirmGateC1._PRESSURE_PIN)
    with patch.object(settings_mgr, "load_settings", lambda: {"desk_pressure_n": "坏值"}):
        T("非法阈值回落缺省 3", ConfirmGateC1._pressure_n() == 3)

# ── 件三/件四：端点失败键统一 + 空 tid 有声账（misc.py 函数体直调）──
# token 门在中间件层不在函数体——401 链条与本格无涉（工单自查：tools 与前端全仓
# grep 无人按 error 键解析这三端点响应，前端唯一消费方 ToolCallBox.tsx 只读 ok）；
# 件四格必须 mock misc._token_audit——真 _token_audit 落 secrets 卷
# （token_audit.jsonl），测试进程绝不写真审计面。
import asyncio
from office.routers import misc as _misc

_r_ap = asyncio.run(_misc.api_approve({"thread_id": "", "tool": "write_file"}))
T("件三 api_approve 空输入：ok=False+reason、error 键绝迹",
  _r_ap.get("ok") is False and "thread_id" in str(_r_ap.get("reason")) and "error" not in _r_ap)
_r_rv = asyncio.run(_misc.api_revoke({"thread_id": "t1", "tool": ""}))
T("件三 api_revoke 缺 tool：ok=False+reason、error 键绝迹",
  _r_rv.get("ok") is False and _r_rv.get("reason") and "error" not in _r_rv)
_r_rb = asyncio.run(_misc.api_reset_budget({}))
T("件三 api_reset_budget 空输入：ok=False+reason（旧帧连 ok 键都没有，本件补齐）且无 error 键",
  _r_rb.get("ok") is False and _r_rb.get("reason") == "需要 thread_id" and "error" not in _r_rb)

_calls = []
with patch.object(_misc, "_token_audit", lambda *a, **k: _calls.append((a, k))):
    _r_rt = asyncio.run(_misc.api_reset_thread({}))
T("件四 reset_thread 空 tid：ok=False+reason 且补落一条失败 token 账"
  "（approval_reset_thread/False/tid=*/reason=missing_thread_id）",
  _r_rt.get("ok") is False and "error" not in _r_rt
  and len(_calls) == 1 and _calls[0][0] == ("approval_reset_thread", False)
  and _calls[0][1].get("tid") == "*" and _calls[0][1].get("reason") == "missing_thread_id")

# ── D：十六轮 D 组/件三护栏扩面——非空输入的**业务帧**（拒/成功）同样禁 error 键 ──
# 401 分层契约（详设计文档）：token 门=中间件层 401，根本不进函数体；函数体
# ok/reason 分层只覆盖已鉴权请求。本格钉三端点语义路径帧形：消费方只许读
# ok/reason/approved/cleared_cards 族键。_token_audit 必须打桩（真函数落 secrets
# 卷 token_audit.jsonl，测试进程零染指）；tid 用不存在的 d2x-none→approve/revoke
# 走"无登记=拒"纯读路径，零状态副作用、不触发 nudge 线程。
with patch.object(_misc, "_token_audit", lambda *a, **k: None):
    _r_ap3 = asyncio.run(_misc.api_approve(
        {"thread_id": "d2x-none", "tool": "write_file", "fp": "0" * 24}))
    T("D api_approve 无待批记录拒帧：ok=False+reason+approved=''，error 键绝迹",
      _r_ap3.get("ok") is False and _r_ap3.get("reason")
      and _r_ap3.get("approved") == "" and "error" not in _r_ap3)
_r_rv3 = asyncio.run(_misc.api_revoke({"thread_id": "d2x-none", "tool": "write_file"}))
T("D api_revoke 无登记帧：仅 ok 一键（set 断言）+ok=False，error 键绝迹",
  _r_rv3.get("ok") is False and "error" not in _r_rv3
  and set(_r_rv3.keys()) == {"ok"})
with patch.object(_misc, "_token_audit", lambda *a, **k: None):
    _r_rb3 = asyncio.run(_misc.api_reset_budget({"thread_id": "d2x-none"}))
T("D api_reset_budget 零卡成功帧：ok=True+cleared_cards=0，error 键绝迹（ok=True 是真 ok——无卡可清也是清成功）",
  _r_rb3.get("ok") is True and _r_rb3.get("cleared_cards") == 0 and "error" not in _r_rb3)

# ── Q：三清扩面（d2v03fix3 件一/二——若若 P1-②实锤 + Cora263 线程持久状态全清单）──
gm._guard_freeze_n["d2q"] = 2                    # 退避梯次：旧版 reset 后残留=救回即永久锁预备
gm._guard_mid["d2q"] = {"tq": [("w", "x")]}      # 误杀降级环历史命中：reset 后观察窗口不该带
gm._guard_hits["d2q"] = [("h", "y")]             # high 命中缓存：同 mid 性质
gm._guard_deny["d2q"] = {"tc_old"}               # 被拒 tc_id：防重放，**reset 后必须在位**
r_q = ConfirmGateC1.reset_thread("d2q")
T("Q 三清扩面（件一/二）：reset 后 freeze_n/mid/hits 全清，deny 刻意保留（防重放安全特性）",
  r_q.get("ok") and "d2q" not in gm._guard_freeze_n and "d2q" not in gm._guard_mid
  and "d2q" not in gm._guard_hits and gm._guard_deny.get("d2q") == {"tc_old"})
gm._guard_deny.pop("d2q", None)

# ── R：竞态格（d2v03fix3 件三/Cora④：setdefault→+=1→判定非原子）──
import threading as _th3
gr = ConfirmGateC1(sub_mode=False)
def _hammer():
    for _ in range(100):
        gr._note_fail(R("write_file", {"file_path": "notes/r.md"}, "rt"), "tool_error")
with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2rt")), \
     patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    _hs = [_th3.Thread(target=_hammer) for _ in range(2)]
    for _h in _hs:
        _h.start()
    for _h in _hs:
        _h.join()
T("R 竞态格（件三/_GATE_LOCK）：双线程同 gk 并发 _note_fail 各 100 次，n=200 不丢数",
  gr._fail_streak["d2rt"]["n"] == 200)
ConfirmGateC1._fail_streak.pop("d2rt", None)
ConfirmGateC1._pressure_notice.pop("d2rt", None)

# ── P 组：上沿账 pin_set:1 + pin_id 三事件（d2v03fix3 件四/五，Cora①②）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    gp = ConfirmGateC1(sub_mode=False)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "d2pin")):
        for _i in ("p1", "p2", "p3"):
            gp.wrap_tool_call(R("write_file", {"file_path": "notes/pin.md"}, _i), err_handler)
        _pv = ConfirmGateC1._PRESSURE_PIN.get("d2pin")
        T("P1 钉值元组形（件五）：(ts, pin_id)，pin_id=钉入ts+tid前4",
          isinstance(_pv, tuple) and len(_pv) == 2 and isinstance(_pv[0], float)
          and _pv[1] == f"{_pv[0]:.1f}-d2pi")
        rec_p = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2pin"]
        T("P2 真落钉帧上沿账（件四）：同帧 pin_set:1+pin_id、downgraded=True",
          len(rec_p) == 1 and rec_p[0].get("pin_set") == 1
          and rec_p[0].get("pin_id") == _pv[1] and rec_p[0].get("downgraded") is True)
        gp._fail_streak["d2pin"] = {"n": 2, "recent": ["q"], "fired": False}
        gp.wrap_tool_call(R("write_file", {"file_path": "notes/pin.md"}, "p4"), err_handler)
        rec_p2 = [x for x in _recs("desk_pressure_downgrade") if x.get("tid") == "d2pin"]
        T("P3 残余帧再触发同带 pin_set:1+同一 pin_id（'钉落下无痕'闭合，单查询一颗钉的一生）",
          len(rec_p2) == 2 and rec_p2[1].get("pin") == 1 and rec_p2[1].get("pin_set") == 1
          and rec_p2[1].get("pin_id") == _pv[1] and rec_p2[1].get("downgraded") is False)
        _tc_p = {"name": "write_file", "args": {"file_path": "notes/pin.md"}, "id": "pz"}
        try:
            gp._process_decision({"type": "approve"}, _tc_p,
                                 {"allowed_decisions": ["approve", "edit", "reject"]})
        except Exception:
            pass  # 官方件对 mock 入参的返回构造不属本格（同 D 组口径）
        rec_pr = [x for x in _recs("desk_pressure_release") if x.get("tid") == "d2pin"]
        T("P4 批准撤钉账带同一 pin_id（release 三路之二/件五）",
          len(rec_pr) == 1 and rec_pr[0].get("pin_id") == _pv[1])
        ConfirmGateC1._PRESSURE_PIN.pop("d2pin", None)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
