# -*- coding: utf-8 -*-
"""r61h 门层测试（hy4 八轮工单第 4/5 条）：
P-1：when 判冻结→tc 入不依赖 TTL 的集合→wrap 先消费出拒信（堵 TTL 竞态 fail-open）；
     c1_decision 无 tid 归一记 "?"。
B-6（r61h 原格）→ P-A 收窄版（爸爸 09-14 夜裁定，plan-deskcontrol-v03 第四节第 5 条）：
     execute→pass 启动必炸不变；write_file/edit_file→pass=auto_edit 档 _SOFTWRITE
     设计路径不再 raise——收窄不开洞的钉：pass 路由下 wrap 内容门仍拒 high 内容
     （私钥字面量实测格，见文件尾 PA 段）。
09-14 续单（full 档镜像格，政令"绝对红线+同档"：full=不请示≠不设防）：
     full 档启动不炸（旧断言下选档即服务起不来=本单实核 P0）；execute 的 pass 路
     内容门补跑——high 拒+落账且不弹卡、普通命令直过、mid 按档义放行；strict 原链零回归。
09-14 续单第二弹（pass 路内容门扩面）：名单再收 delete/dispatch_to_xiaoquan/
     dispatch_external/start_async_task/edit_memory——full 档这四手原零扫描直过；
     扫描入参按 args 形态适配既有通道（delete 路径走写侧后门路径规则、派活文本走
     dispatch 规则、edit_memory 内容走写侧内容规则）。本格钉：high 拒×3、
     普通操作不误伤×3、落账、strict 扩面手仍走 ask（pass 分支零染指）。
hy4 九轮 N-4（末段 N4 格）：冻结拒信解除时限读退避真源（30m→1h→2h→永久，
     永久文案含 /approvals/guard_unlock 指引）；guard_unlock 收门侧真源类方法
     ConfirmGateC1.guard_unlock——三集合同清（lock/streak/hold，防解封后
     误吃一次接力拒信）。⚠ misc.py 端点本体改调此件是一行委托、不在本单白名单，
     集成待主会话落（交卷已注明）。本格钉的是门侧真源行为，端点集成态未测（交卷"越墙见闻"已注明）。
09-15 r61k 第二笔（A 格，文件尾）：端点委托已落地并补上 hy4 点名的集成钉——**不带
     token、不动生产账**直调 misc.api_guard_unlock（approvals._audit 指 temp 于文件
     首；_token_audit 原件写 secrets 卷 token_audit.jsonl，本格 stub 进内存），
     断言 cleared=1、三集合全清、guard_unlock 账落 temp；另带 cleared=0 前提格
     （不存在 tid→ok:false+reason；d2v03fix3⑤ 命名债前为 hint）。上段"端点集成态未测"仅追平到九轮为止。
需 langchain：容器内跑（test_c1_hook 同法），宿主用 D:\\m\\workspace\\.venv。"""
import os, sys, json, time, tempfile
sys.path.insert(0, os.environ.get("MIA_SRC", r"D:\m\workspace"))
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
import approvals as ap  # noqa: E402
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402

tmp = tempfile.mkdtemp(); ap._AUDIT_PATH = os.path.join(tmp, "a.jsonl")

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

# ── P-1 接力格：半批冻结 tc 的 when→wrap 拒信链（含 TTL 竞态格）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()  # strict 三工具=ask，B-6 断言全过能起来=正向格
    T("B6 strict 档启动不炸（三工具=ask）", True)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "r61h")):
        w = g._make_when("execute")
        g._guard_lock["r61h"] = (time.time(), 1800.0)  # 纯冻结态（本 tc 自身未命中 high）
        class RA:
            tool_call = {"name": "execute", "id": "tcA", "args": {"command": "ls"}}
        T("P1 when：冻结线程 ask 调用不弹卡", w(RA()) is False)
        T("P1 when：排除出卡的 tc 入不依赖 TTL 集合",
          "tcA" in (g._frozen_hold.get("r61h") or set()))
        # 竞态格：when→wrap 之间锁恰好 TTL 到期——_frozen 已 False，旧版此处 fail-open
        g._guard_lock["r61h"] = (time.time() - 99999, 1.0)
        msg = g._check_budget_gate(RA())
        T("P1 wrap：TTL 到期仍吃冻结拒信（不敞怀执行）",
          msg is not None and "冻结" in msg.content)
        T("P1 接力集合消费即清（拒一次语义，同 _guard_deny 口径）",
          "tcA" not in (g._frozen_hold.get("r61h") or set()))
        T("P1 同 tc 二次 wrap 不再连拒（锁到期后放行）",
          g._check_budget_gate(RA()) is None)
        # 接力链基线：锁未到期时同样由集合出拒信（文案与 _frozen 直判分支同源）
        g._guard_lock["r61h"] = (time.time(), 1800.0)
        class RB:
            tool_call = {"name": "execute", "id": "tcB", "args": {"command": "ls"}}
        T("P1 再冻结：新 tc 继续登记", w(RB()) is False and "tcB" in g._frozen_hold["r61h"])
        msgB = g._check_budget_gate(RB())
        T("P1 wrap：冻结未到期接力拒", msgB is not None and "冻结" in msgB.content)
        # ── P-1(2)：c1_decision 无 tid 记 "?" 不再记空串 ──
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "")):
            g._process_decision({"type": "approve"},
                                {"name": "execute", "args": {"command": "ls"}, "id": "z1"},
                                {"allowed_decisions": ["approve"]})
        rec = [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
               if '"c1_decision"' in l][-1]
        T("P1 无 tid 落账记 '?'（与真缺失区分）", rec.get("tid") == "?")

# ── B-6→P-A 收窄断言格（爸爸 09-14 夜裁定，plan-deskcontrol-v03 第四节第 5 条）：
#    execute→pass 启动必炸不变；write_file/edit_file→pass 是 auto_edit _SOFTWRITE
#    设计路径，不再误炸（假 _decision monkeypatch）──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    fake = lambda name, level, args: ("pass" if name == "execute" else "ask")
    with patch.object(ConfirmGateMiddleware, "_decision", staticmethod(fake)):
        raised = None
        try:
            ConfirmGateC1(sub_mode=False)
        except RuntimeError as e:
            raised = str(e)
    T("B6/PA execute→pass 启动必炸", raised is not None and "execute" in raised)
    for t in ("write_file", "edit_file"):
        fake2 = lambda name, level, args, _t=t: ("pass" if name == _t else "ask")
        with patch.object(ConfirmGateMiddleware, "_decision", staticmethod(fake2)):
            boom = None
            try:
                ConfirmGateC1(sub_mode=False)
            except Exception as e:
                boom = repr(e)
        T(f"PA {t}→pass 不误炸（softwrite 设计路径）", boom is None)
    for dec in ("ask", "deny", "selflock"):
        with patch.object(ConfirmGateMiddleware, "_decision",
                          staticmethod(lambda name, level, args, _d=dec: _d)):
            try:
                ConfirmGateC1(sub_mode=False); boom = False
            except Exception:
                boom = True
        T(f"B6 路由 {dec} 不误炸", not boom)
    # 断言只管主层：子层构造在 pass 路由下不跑断言（`if not sub_mode` 半边覆盖）
    with patch.object(ConfirmGateMiddleware, "_decision",
                      staticmethod(lambda name, level, args: "pass")):
        try:
            ConfirmGateC1(sub_mode=True); sb_ok = True
        except Exception:
            sb_ok = False
    T("B6 子层不跑断言（pass 路由仍可构造）", sb_ok)

# ── PA 补洞钉格：auto_edit 档 write_file 路由 pass（设计路径成立），但 wrap 内容门
#    必须仍拒 high 内容——09-14 实核结论：when 侧 `dec != "ask"` 短路，pass 路由原本
#    跳检（真洞，非回归钉），本格钉住 _check_budget_gate pass 分支的补跑。──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    g3 = ConfirmGateC1(sub_mode=False)  # auto_edit 下 execute=ask，收窄断言应放行构造
    T("PA auto_edit 档启动不炸（execute=ask，write/edit 不再参与断言）", True)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "pa1")):
        _pk = ("-----BEGIN " + "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1r\n"
               "-----END OPENSSH PRIVATE KEY-----")  # 拆词构造：别让本测试文件自己中扫描
        T("PA 前提：auto_edit write_file 路由=pass（_SOFTWRITE 设计路径真实存在）",
          g3._route("write_file", {"file_path": "notes/out.md", "content": _pk}) == "pass")
        class RW:
            tool_call = {"name": "write_file", "id": "tcP1",
                         "args": {"file_path": "notes/out.md", "content": _pk}}
        mW = g3._check_budget_gate(RW())
        T("PA auto_edit write_file 私钥内容→wrap 仍拒",
          mW is not None and "安全门" in mW.content)
        class RE:
            tool_call = {"name": "edit_file", "id": "tcP2",
                         "args": {"file_path": "notes/out.md", "new_string": _pk}}
        mE = g3._check_budget_gate(RE())
        T("PA auto_edit edit_file 私钥内容→wrap 仍拒",
          mE is not None and "安全门" in mE.content)
        class RN:
            tool_call = {"name": "write_file", "id": "tcP3",
                         "args": {"file_path": "notes/out.md", "content": "今天会议纪要：门在，正常写字。"}}
        T("PA 普通软写不误杀（wrap 放行执行）", g3._check_budget_gate(RN()) is None)
        # 拒必须落账（when 侧 guard_high 同规格）——"门没了+没人知道"双倍失败教训
        recs = [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
                if '"guard_high"' in l]
        T("PA pass 路 high 拒落 guard_high 账",
          any(r.get("tool") in ("write_file", "edit_file") for r in recs))

# ── 09-14 续单 full 档镜像格（知夏方案，政令"绝对红线+同档"：full=不请示≠不设防）：
#    ①启动断言 full 豁免——选档不许退化成"服务起不来"（本单实核 P0）；
#    ②full 档 execute 路由=pass 照旧无卡直过，但 high 命令（rm 根/系统目录形态）被
#      wrap 内容门拒+落 guard_high 账——拒是机制不是请示，不违"不问"语义；
#    ③普通命令直过、mid 按档义放行（无卡档=选档时已接受，拒=日常全变误杀）；
#    ④strict 档原机器门链（when 检→_guard_deny 登记→wrap 拒信）零回归。──
_rmroot = "rm -" + "rf /etc"  # 拆词构造：本测试文件自身别中扫描规则（_pk 格同法）
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "full")):
    boom4 = None
    try:
        g4 = ConfirmGateC1(sub_mode=False)  # full 下 execute=pass——豁免前此处必炸
    except Exception as e:
        boom4 = repr(e)
    T("FULL full 档启动不炸（断言豁免，修法①）", boom4 is None)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "full1")):
        T("FULL 前提：execute 路由=pass（不请示档义成立）",
          g4._route("execute", {"command": _rmroot}) == "pass")
        class RX:
            tool_call = {"name": "execute", "id": "tcX1", "args": {"command": _rmroot}}
        T("FULL high 命令 when 不弹卡（修法②：无卡语义不变，从头到尾没卡可弹）",
          g4._make_when("execute")(RX()) is False)
        mX = g4._check_budget_gate(RX())
        T("FULL execute high→wrap 内容门拒（修法②：拒是机制不是请示）",
          mX is not None and "安全门" in mX.content)
        T("FULL high 拒落 guard_high 账（tool=execute，与 write 侧同规格）",
          any(r.get("tool") == "execute" for r in
              [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
               if '"guard_high"' in l]))
        class RL:
            tool_call = {"name": "execute", "id": "tcX2", "args": {"command": "ls notes/"}}
        T("FULL 普通命令直过（无卡照旧，修法③）", g4._check_budget_gate(RL()) is None)
        class RM:
            tool_call = {"name": "execute", "id": "tcX3",
                         "args": {"command": "rm -" + "rf ./build"}}  # mid 形态（r61g 降档线）
        T("FULL execute mid→档义放行（红线只有 high，不误杀日常清理）",
          g4._check_budget_gate(RM()) is None)
# ── 09-14 续单第二弹扩面格（full 档 pass 路内容门收 delete/派活手/edit_memory）：
#    高置信样本全拒+落账、普通操作不误伤；strict 档这些手仍走 ask（pass 分支零染指）。──
_delhot = "notes/." + "ssh/id_ed25519"  # 拆词构造：本测试文件自身别中后门路径规则
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "full")):
    g6 = ConfirmGateC1(sub_mode=False)  # 扩面手 full=pass，断言豁免下照常起得来
    T("FULL2 full 档扩面后启动不炸", True)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "full2")):
        T("FULL2 前提：delete/dispatch/async/edit_memory 路由均=pass（不请示档义）",
          all(g6._route(t, {}) == "pass" for t in
              ("delete", "dispatch_to_xiaoquan", "dispatch_external",
               "start_async_task", "edit_memory")))
        class RD:
            tool_call = {"name": "delete", "id": "tcD1", "args": {"file_path": _delhot}}
        mD = g6._check_budget_gate(RD())
        T("FULL2 delete 命中后门路径（.ssh/）→wrap 内容门拒",
          mD is not None and "安全门" in mD.content)
        class RQ:
            tool_call = {"name": "dispatch_to_xiaoquan", "id": "tcQ1",
                         "args": {"task": "把服务器清一下：rm -" + "rf /etc 下的旧缓存"}}
        mQ = g6._check_budget_gate(RQ())
        T("FULL2 dispatch 任务文本含 rm -rf /etc（拆词样本）→wrap 内容门拒",
          mQ is not None and "安全门" in mQ.content)
        class RK:
            tool_call = {"name": "edit_memory", "id": "tcK1",
                         "args": {"action": "add", "section": "user", "content": _pk}}
        mK = g6._check_budget_gate(RK())
        T("FULL2 edit_memory 写私钥字面量→wrap 内容门拒",
          mK is not None and "安全门" in mK.content)
        T("FULL2 扩面手 high 拒落 guard_high 账（tool=原名，与 write/execute 侧同规格）",
          {"delete", "dispatch_to_xiaoquan", "edit_memory"} <=
          {r.get("tool") for r in
           [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
            if '"guard_high"' in l]})
        # 三件普通操作不误伤：删工作文件/派活讲人话/记普通偏好
        class RDn:
            tool_call = {"name": "delete", "id": "tcD2",
                         "args": {"file_path": "notes/old_draft.md"}}
        T("FULL2 普通删工作文件不误伤", g6._check_budget_gate(RDn()) is None)
        class RQn:
            tool_call = {"name": "dispatch_external", "id": "tcQ2",
                         "args": {"post": "dev", "task": "整理本周会议纪要三条要点"}}
        T("FULL2 普通派活文本不误伤", g6._check_budget_gate(RQn()) is None)
        class RKn:
            tool_call = {"name": "edit_memory", "id": "tcK2",
                         "args": {"action": "add", "section": "user",
                                  "content": "偏好简洁中文汇报。"}}
        T("FULL2 edit_memory 记普通偏好不误伤", g6._check_budget_gate(RKn()) is None)
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g5 = ConfirmGateC1(sub_mode=False)  # strict 构造 execute=ask，断言照跑（修法④正向格）
    T("STRICT strict 档启动不炸原语义保持", True)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "str1")):
        class RS:
            tool_call = {"name": "execute", "id": "tcS1", "args": {"command": _rmroot}}
        T("STRICT 零回归：execute high 仍走 when 强制拦链（_guard_deny 登记）",
          g5._make_when("execute")(RS()) is False
          and "tcS1" in (g5._guard_deny.get("str1") or set()))
        mS = g5._check_budget_gate(RS())
        T("STRICT 零回归：wrap 拒信仍出自机器门原通道",
          mS is not None and "机器安全门拦截" in mS.content)
        T("STRICT 零回归：扩面手（delete/派活/edit_memory）仍走 ask——pass 分支零染指",
          all(g5._route(t, {}) == "ask" for t in
              ("delete", "dispatch_to_xiaoquan", "dispatch_external",
               "start_async_task", "edit_memory")))

# ── N-4（hy4 九轮）：冻结拒信文案读退避真源（不再硬编码"30 分钟"）；永久锁指向
#    guard_unlock；门侧真源类方法三集合同清，解封后不再误吃一次接力拒信。
#    ⚠ 端点本体在 misc.py（白名单外），以下钉的是门侧真源行为，非端点集成态
#    （集成态由文件尾 r61k A 格补钉）。──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g7 = ConfirmGateC1(sub_mode=False)
    for _tid_, _ttl_, _want_, _absent_ in (
            ("n4b", 3600.0, "1 小时", "30 分钟"),   # 第二次冻结：退避 1h
            ("n4c", 7200.0, "2 小时", "30 分钟"),   # 第三次退避档 2h（永久另格）
    ):
        with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda t=_tid_: t)):
            g7._guard_lock[_tid_] = (time.time(), _ttl_)
            class RN4:
                tool_call = {"name": "execute", "id": "tc_" + _tid_,
                             "args": {"command": "ls"}}
            T(f"N4 {_tid_} when：冻结线程登记 hold", g7._make_when("execute")(RN4()) is False)
            m7 = g7._check_budget_gate(RN4())
            T(f"N4 拒信时限读退避真源（{_want_}，非硬编码 30 分钟）",
              m7 is not None and _want_ in m7.content and _absent_ not in m7.content)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "n4p")):
        g7._guard_lock["n4p"] = (time.time(), float("inf"))
        class RP:
            tool_call = {"name": "execute", "id": "tc_p", "args": {"command": "ls"}}
        g7._make_when("execute")(RP())
        mp = g7._check_budget_gate(RP())
        T("N4 永久冻结文案含「永久」与 guard_unlock 出口指引",
          mp is not None and "永久" in mp.content and "/approvals/guard_unlock" in mp.content)
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "n4u")):
        g7._guard_lock["n4u"] = (time.time(), float("inf"))
        g7._guard_streak["n4u"] = [time.time(), time.time()]
        class RU:
            tool_call = {"name": "execute", "id": "tc_u", "args": {"command": "ls"}}
        g7._make_when("execute")(RU())  # 冻结态：hold 登记 tc_u
        T("N4 解封前 hold 已登记（前提格）", "tc_u" in (g7._frozen_hold.get("n4u") or set()))
        n_u = ConfirmGateC1.guard_unlock("n4u")
        T("N4 真源件 cleared=1 且 lock/streak 清",
          n_u == 1 and "n4u" not in g7._guard_lock and "n4u" not in g7._guard_streak)
        T("N4 解封同时清 _frozen_hold（防解封后误吃一次接力拒信）",
          "tc_u" not in (g7._frozen_hold.get("n4u") or set()))
        T("N4 解封后同 tc wrap 不误拒（放行执行）", g7._check_budget_gate(RU()) is None)

# ── A 格（09-15 r61k 第二笔，hy4 点名的集成钉）：misc.py guard_unlock 端点直调——
#    不带 token、不动生产账：ap._AUDIT_PATH 已在文件首指 temp；_token_audit 原件写
#    secrets 卷（token_audit.jsonl），此处 patch 成内存 stub（端点模块属性，函数体
#    按 global 查得——patch 有效）。钉死"端点一行委托→真源三集合同清→落账"全链，
#    外加 cleared=0 前提格（hy4 十轮端点侧点1：静默 ok:true=双倍失败）。──
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    import asyncio
    from office.routers import misc as _misc
    g8 = ConfirmGateC1(sub_mode=False)  # 构造即入 _GATE_INSTANCES 花名册（委托链前提）
    _ta = "r61k-a"
    g8._guard_lock[_ta] = (time.time(), float("inf"))  # 手工冻结一个 tid（永久锁档）
    g8._guard_streak[_ta] = [time.time(), time.time()]
    g8._frozen_hold[_ta] = {"tc_a"}                    # when 侧登记过的接力 hold
    _stub = []
    with patch.object(_misc, "_token_audit",
                      lambda action, ok, **kw: _stub.append((action, bool(ok), kw))):
        r_a = asyncio.run(_misc.api_guard_unlock({"thread_id": _ta}))
        stub_a = list(_stub)
        rec_a = [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")
                 if '"guard_unlock"' in l]
        r_n = asyncio.run(_misc.api_guard_unlock({"thread_id": "no-such-tid-r61k"}))
        stub_n = list(_stub)
    T("A 端点集成：真实冻结 tid → cleared=1 且 ok=true",
      r_a.get("ok") is True and r_a.get("cleared") == 1)
    T("A 端点集成：三集合（lock/streak/hold）全清",
      _ta not in g8._guard_lock and _ta not in g8._guard_streak
      and _ta not in g8._frozen_hold)
    T("A 端点集成：guard_unlock 账落 temp（cleared=1/by=admin），token 账走 stub 不落生产",
      bool(rec_a) and rec_a[-1].get("cleared") == 1 and rec_a[-1].get("by") == "admin"
      and len(stub_a) == 1 and stub_a[0][0] == "approval_guard_unlock"
      and stub_a[0][1] is True)
    T("A 前提格：不存在 tid → cleared=0 给 ok:false+reason（不再静默 ok:true；d2v03fix3⑤ hint 退役）",
      r_n.get("ok") is False and r_n.get("cleared") == 0 and str(r_n.get("reason") or "") != ""
      and "hint" not in r_n and stub_n and stub_n[-1][1] is False)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
