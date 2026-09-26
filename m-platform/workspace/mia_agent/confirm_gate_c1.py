"""C1 确认门 v2——官方 HumanInTheLoopMiddleware 包装版（r41）。

设计稿：notes/plan-c1-hitl-20260911.md（官方件 506 行源码对账+四家约束全落）。
分层架构（Eve"双路并存乱"根治：ask 通道只剩一条）：

  1. SelfLockDenyGate（wrap_tool_call 薄件）：自锁硬拒 + plan 档 deny 硬拦。
     官方件只有"问/不问"两个出口、没有"拒绝"出口——拒类走本件（ToolMessage error），
     且 C1 的 when 谓词对这两类返回 False（静默放行到本件门口被拒），不打扰爸爸。
  2. ConfirmGateC1(HumanInTheLoopMiddleware)：ask 批量卡。
     - after_model 前动态反选注册：state 里出现的每个工具名（含 MCP/未知）都入名单
       ——Cora R74 反选原则，官方"未列名=自动放行"的 fail-open 被堵死。
     - when 谓词=档位路由器：plan/只读→False；auto_edit 墙内写→False；strict ask→True。
     - decisions 原生恢复：批量 HITLRequest 一卡 N 行，reject 自带勿重试文案，
       edit 支持爸爸改参数再跑（v0.2 前端按钮）。
     - approve 即执行（官方 after_model 直接改写 tool_calls），无重试循环——
       16 次批准病的根（wrap_tool_call 拦截后模型反复重生成）在架构层消失。
"""
from __future__ import annotations

import re
import threading
from typing import Any

from langchain.agents.middleware.human_in_the_loop import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

# r46：全盘 find 形态（与观测器 _FULL_FIND 同义——gate 侧硬拒用，观测侧照旧只记）
_FULLFIND = re.compile(r"find\s+/(?:\s|$)")


class SelfLockDenyGate:
    """拒类薄件（selflock/plan-deny）。接口对齐 deepagents middleware：wrap_tool_call。
    不含任何 ask 分支——请示全部走 ConfirmGateC1 的批量卡。
    判定/文案直引现役 ConfirmGateMiddleware 静态真源（不注入，防未绑定引用）。"""

    def __init__(self, sub_mode: bool = False):
        self.sub_mode = sub_mode
        # 文案/判定代理：复用现役门实例方法（_block_msg/_args_preview 依赖实例态），
        # 真源不复制不注入——名单漂移零风险。
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        self._proxy = ConfirmGateMiddleware(sub_mode=sub_mode)

    def _guard(self, request, handler, awaitable: bool):
        tc = getattr(request, "tool_call", None) or {}
        name = tc.get("name", "?")
        level = self._proxy._level()
        dec = self._proxy._decision(name, level, tc.get("args"))
        if dec in ("selflock", "deny"):
            return ToolMessage(
                content=self._proxy._block_msg(name, level, dec, tc.get("args")),
                tool_call_id=tc.get("id", ""),
            )
        return None  # 放行：由调用方继续 handler

    def wrap_tool_call(self, request, handler):
        blocked = self._guard(request, handler, awaitable=False)
        return blocked if blocked is not None else handler(request)


class ConfirmGateC1(HumanInTheLoopMiddleware):
    """ask 批量卡（官方件包装）+ 拒类自兜底（Lyra R41-P0：to_deny 不依赖外部薄件）。

    用法：主图 middleware = [ConfirmGateC1(sub_mode=False)]（自包含，两钩子）；
    子层（牛马/部门图）= [SubGate(sub_mode=True)]——ask 不弹卡转文案沿链上报（Eve/Lyra：
    子图 interrupt 无人批=挂死）。

    两钩子分工：
    - after_model：动态反选注册（堵官方 fail-open）→ when=档位路由（ask→True 弹官方批量卡）
    - wrap_tool_call：to_deny（selflock/plan-deny）直接 ToolMessage 拒——不依赖外部件，
      自锁防线自包含；批准恢复后的执行同样过本钩子（接线前必测1 验证）。
    判定单一真源：全部走 _proxy._decision 四态映射，本类不重写判定逻辑（Cora R41-P1-1）。
    """

    # r61k 卫生项（hy4 十轮）：花名册声明原夹在类名与文档字符串之间，把 __doc__ 吃成
    # None——挪到 docstring 之后恢复。实例只增不减的隐患 hy4 判非本轮，只记此账不修。
    _GATE_INSTANCES: list = []  # r61b：活实例花名册（guard_unlock 端点经此触达 _guard_lock）

    _PROXY = None  # 模块级单例（Eve 新炮1：档位读取入口统一+省实例化）

    # D2 压力降档（plan-d2-pressure-v1，09-15 爸爸批 N=3）：连败达阈时本线程临时钉
    # strict。类级而非实例级——读档入口 read_level 是 classmethod，且钉的是"线程"
    # 不是"门实例"（花名册多实例时不该各钉一份）。真源不动：settings 唯一写入口
    # （设置页）零染指；新线程天然无键=自然重置；撤钉只认批准卡放行（_process_decision）。
    # 仅真 tid 可钉（"? 桶共享"案 r61b P1-2 同规——无 tid 只落账+告知，不跨线程连坐）。
    # d2v03fix3⑤（Cora②）：值=(钉入时刻, pin_id) 二元组，pin_id=钉入ts+tid前4——
    # downgrade/release（ttl/批准/reset 三路）/desk_state_reset 账三事件统一带 pin_id，
    # "一颗钉的一生"单查询可追；_pin_alive 解包同步跟改（全仓唯一写点是 _pressure_fire）。
    # d2v03fix3⑩（Cora③b 现状明说）：每层独立钉（子层读自身 tid），父钉不传导子层
    # ——传导设计另单（v0.3 三选项）。
    _PRESSURE_PIN: dict = {}  # {tid: (钉入时刻, pin_id)}

    # D2 挂账四件②（hy4 十二轮 N2，09-15 爸爸令动工）：计数与告知上提类级——
    # 钉是类级而 streak 是实例级=不对称：花名册多实例时 A 攒 2、B 攒 2 谁都不触发，
    # 或 A 触发钉全局、B 从 0 再攒。self._fail_streak 等引用经实例查找自动落到类属性，
    # 全链语义不变（键仍是 gk=tid，"? 桶共享"同规）。
    _fail_streak: dict = {}      # {gk: {"n": 连败数, "recent": [最近≤3条脱敏摘要], "fired": 本轮已否触发降档}}
    _pressure_notice: dict = {}  # {gk: 降档告知一行}（下一次拒信/卡面附一行，消费即清）

    # d2v03fix3③（Cora④）：类级门闸——以下受保护持久状态（类级与实例级混合，
    # 09-16 二十轮 hy3 措辞对齐：_guard_hits 实为实例属性）的读-改-写路径
    # （setdefault→+=1→判定）非原子，双线程交错=丢更新。RLock 可重入：
    # _note_fail→_pressure_fire、level_and_source→_pin_alive 同线程嵌套不受阻。
    # 只闸 dict 变更临界区，不闸 scan/渲染等慢路径。
    _GATE_LOCK = threading.RLock()

    # v0.3 件二（plan-d2-v03 §件二，十六轮裁决②改址）：force 审计链的最后一道死信——
    # mia_home/runtime/bypass_deadletter.jsonl。**与主账（mia_home/notes/
    # approvals_log.jsonl）刻意分离**：同目录=兜底与被保护对象同故障域，且备份脚本
    # 可能把死信一并回滚（"钥匙挂被锁者墙上"同族病）。None=首次写时惰性生成
    # （ap._AUDIT_PATH 同款：模块两侧被 import，路径只在动手时才落文件系统）。
    # 文件与 runtime/ 目录运行时生成不预建；测试侧直接赋值本属性即改道 temp。
    _DEADLETTER_PATH = None

    @classmethod
    def _pin_ttl(cls) -> int:
        """D2 挂账四件①（hy4 十二轮 P-A）：钉 TTL——"临时钉"原进程内实为永久
        （不成功/不批准就跨天钉着，名不副实）。缺省 24h；settings 顶层键
        desk_pressure_pin_ttl_s 可调（读法同 _pressure_n，不写配置文件，L26 不破）。"""
        try:
            from settings_mgr import load_settings
            v = int((load_settings() or {}).get("desk_pressure_pin_ttl_s", 86400))
            return v if v >= 60 else 86400
        except Exception:
            return 86400

    @classmethod
    def _pin_alive(cls, tid: str) -> bool:
        """钉存活判定+惰性到期自清（read_level 每回合经过此门=无需独立清扫器）。
        到期撤钉落账 desk_pressure_release reason=ttl——撤钉有声（N1 半本账口径补齐）。
        d2v03fix3⑤：值解包跟改 (ts, pin_id)，ttl 撤钉账带 pin_id（release 三路之一）。
        d2v03fix3③：查在否→比 TTL→弹出是读-改-写，双线程同 tid 会双落 ttl 账——入闸。"""
        with cls._GATE_LOCK:
            v = cls._PRESSURE_PIN.get(tid)
            if v is None:
                return False
            ts, pin_id = v
            import time as _t
            if _t.time() - ts > cls._pin_ttl():
                cls._PRESSURE_PIN.pop(tid, None)
                try:
                    import approvals as _ap
                    _ap._audit("desk_pressure_release", thread_id=tid, reason="ttl",
                               **({"pin_id": pin_id} if pin_id else {}))
                except Exception:
                    pass
                return False
            return True

    @classmethod
    def _proxy_of(cls):
        if cls._PROXY is None:
            from mia_agent.confirm_gate import ConfirmGateMiddleware
            cls._PROXY = ConfirmGateMiddleware(sub_mode=False)
        return cls._PROXY

    @classmethod
    def level_and_source(cls) -> tuple[str, str]:
        """v0.3 件一（plan-d2-v03 §件一）：档位+来源单一判定处——治"钉存活≠钉生效"
        残余帧（真源在钉存续期内被爸爸改成 strict 且钉未到期，旧"lvl==strict 且
        _pin_alive"二次推断此刻会报"临时降档"=话术成谎）。规则：真源高档
        （strict/plan）直接返回 (level,"true")，钉不参与；低档才查活钉，
        活钉 → ("strict","pin")，无钉/到期（_pin_alive 惰性自清，只调这一次）→
        (level,"true")。source ∈ "true" | "pin"，消费端（SubGate 话术）据此出文案。
        D2 压力降档背景：本线程被钉时读档侧临时覆盖（不动 settings 真源）。
        tid 来源（十六轮裁决②采纳项）：cls._tid() 单点读取——即 langgraph
        config 的 thread_id；空串=无线程上下文=不查钉（"? 桶不连坐"钉同款规矩）。
        plan 比 strict 更硬（变更硬拦），真源 strict 本就等于降档目标——两者都
        不参与覆盖（"已在 strict/plan 不重复降"），绝不允许覆盖反把 plan 放软。"""
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        level = ConfirmGateMiddleware._level()  # 类级直调（staticmethod 真源，NOVA P0-3 入口统一）
        if level not in ("strict", "plan"):
            tid = cls._tid()
            if tid and cls._pin_alive(tid):
                return "strict", "pin"
        return level, "true"

    @classmethod
    def read_level(cls) -> str:
        """返回**生效档**（可被压力钉抬成 strict），不是设置页真源——十六轮裁决②：
        旧调用点若拿本方法当"设置有没有被改"的真源用即为误用，读真源请直调
        ConfirmGateMiddleware._level()。"""
        return cls.level_and_source()[0]  # v0.3 件一：单行委托判定处（旧调用点零改动）

    @classmethod
    def guard_unlock(cls, tid: str = "") -> int:
        """r61h 九轮 N-4（hy4 九轮）：手动解冻动作收进门侧单一真源——misc.py 的
        /approvals/guard_unlock 端点原直接 pop _guard_lock/_guard_streak，漏清
        _frozen_hold：解封后 when 侧残留的接力登记仍会被 wrap 消费一次=误吃冻结拒信。
        本件三集合同清（lock/streak/hold）。端点侧改调本方法是一行委托——r61j 已落，
        r61k 格 A 已钉集成回归（test_r61h_gates.py 尾段）。返回 cleared 计数口径同旧端点
        （guard_unlock/guard_ttl_release 落账仍在调用方，本件不动账）。"""
        cleared = 0
        for g in cls._GATE_INSTANCES:
            for k in ([tid] if tid else list(g._guard_lock.keys())):
                if k in g._guard_lock:
                    g._guard_lock.pop(k, None)
                    g._guard_streak.pop(k, None)
                    # hold 键=gk（when 侧 `tid or "?"`；冻结须真 tid，两者在此同源）
                    g._frozen_hold.pop(k, None)
                    cleared += 1
        return cleared

    @classmethod
    def _clear_three_locks(cls, tid: str) -> None:
        """v0.3 件二抽出：三清动作单一真源（M3 正序"落账成功才清"与 force 倒序
        "先清再落账"共用同一把扫帚，两条路径永不漂移）——guard_unlock 是冻结锁
        单一真源（lock/streak/hold 三集合同清），超预算两表、压力钉、streak、
        notice 在此齐扫。纯 dict 操作，不会失败。
        d2v03fix3①②（若若 P1-②实锤+Cora 263"线程持久状态全清单"扩面）：
        - _guard_freeze_n **清**——旧版不清，force 救回的线程保留退避梯次，下次连撞
          直接 ttl=inf 永久锁（"刚救回一步回永久冻结"）；
        - _guard_mid/_guard_hits **清**（Cora 判词：reset 后观察窗口不该带历史，
          误杀降级环判据被 reset 前命中污染）；
        - _guard_deny **刻意保留**（防重放安全特性，判词见其声明处注释，清=回退）；
        - _guard_lock/_guard_streak/_frozen_hold 清（guard_unlock 原有，不重复列账）。
        每件"清/留"判词齐=全清单过一遍，别再只修名单上那一个。"""
        with cls._GATE_LOCK:  # d2v03fix3③（Cora④）：清扫与 when 侧钉/冻结读-改-写互斥
            cls.guard_unlock(tid)
            for g in cls._GATE_INSTANCES:
                for attr in ("_over_budget", "_abs_blocked",
                             "_guard_freeze_n", "_guard_mid", "_guard_hits"):
                    _bucket = getattr(g, attr, None)
                    if _bucket:
                        _bucket.pop(tid, None)
            cls._PRESSURE_PIN.pop(tid, None)
            cls._fail_streak.pop(tid, None)
            cls._pressure_notice.pop(tid, None)

    @classmethod
    def _deadletter_default(cls) -> str:
        """死信缺省新址（十六轮裁决②）：mia_home/runtime/bypass_deadletter.jsonl——
        与主账 notes/ 分离，理由见 _DEADLETTER_PATH 注释。拆成独立判定处是为了
        测试可断言缺址本身（M6 格），不靠真写生产目录验证。"""
        import os as _os
        return _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "mia_home", "runtime", "bypass_deadletter.jsonl")

    @classmethod
    def _deadletter_dump(cls, tid: str, snap: dict, err: str,
                         stage: str = "", cleared: bool = True) -> None:
        """v0.3 件二（十六轮裁决②三改）：force 路任一环节失败时的死信兜底——
        mia_home/runtime/bypass_deadletter.jsonl 追加一行，字段含 ts/tid/异常类名/
        stage（"clear_locks"|"audit"——触发面扩后读账人必须能分清"锁清了账没落"
        与"清锁本身抛、锁可能半清"的部分成功态）/cleared/forced_reset 标记/
        清前三锁计数快照（snap 永远是清锁动作之前的 peek，不做事后诸葛）。
        **无轮转 + 单行一次写入**（兜底不是日志系统：只追加、不切割、不回放）。
        写这步也抛照样吞（print 直出字段原样）——死信之死信落盘无意义，静默更无；
        本方法**永不向上抛**：force 出口 ok=True 无条件的承诺不能被兜底自己反杀。
        hy4 十七轮②：两行 import 挪进 try 首行——"永不向上抛"是**结构保证**不是
        经验常态（os 几乎必载/json 大概率已载都不算数：调用点在 reset_thread 的
        except 块内，此处一抛就顶掉原异常且外层无二次兜底，force 出口直接 500）；
        except 支只 print，不依赖 _j/_os，挪动零副作用。"""
        try:
            import json as _j
            import os as _os
            line = _j.dumps({"ts": round(__import__("time").time(), 1),
                             "ev": "bypass_deadletter", "tid": tid, "err": err,
                             "stage": stage, "cleared": cleared,
                             "forced_reset": True, **snap},
                            ensure_ascii=False)
            if cls._DEADLETTER_PATH is None:
                cls._DEADLETTER_PATH = cls._deadletter_default()
            _os.makedirs(_os.path.dirname(cls._DEADLETTER_PATH), exist_ok=True)
            with open(cls._DEADLETTER_PATH, "a", encoding="utf-8") as _fh:
                _fh.write(line + "\n")
        except Exception as _de:
            print(f"[gate] bypass 死信写失败（字段原样直出）：{_de} "
                  f"tid={tid} err={err} stage={stage} cleared={cleared} snap={snap}",
                  flush=True)

    @classmethod
    def reset_thread(cls, tid: str, force: bool = False) -> dict:
        """D2 挂账四件④（hy4 十二轮 P-B，09-15 爸爸令动工）：三锁叠加的唯一总出口。
        冻结（guard_lock）+超预算（_over_budget/_abs_blocked）+压力钉（_PRESSURE_PIN）
        三把同时扣住时，guard_unlock 只开第一把，而"批准卡放行"这条唯一解压路径在
        无卡/超预算态走不到=线程死锁爸爸也救不回。本方法三锁齐清并落账
        desk_state_reset（P-B 明令：必须落账；经此通道撤钉不落 desk_pressure_release——
        那本账只认批准放行/TTL 到期两个出口，此处只见 desk_state_reset.pressure=1，
        读账人查此）。approvals 侧卡片配额计数由端点侧
        另调 _ap.reset_task_cards 清（与 /approvals/reset 同源，不在此双写）。
        只认真 tid（"? 桶"不连坐，钉同款规矩）。
        budget 为两表命中数之和（单实例最多 2），非线程数——明细另落 budget_detail
        分列，读账人拿 budget 当"几个线程超预算"会算错。

        hy4 十四轮 §⑤（本单主项）：**先算 → 先落账 → 落账成功才清锁**。
        旧序是"清三锁→落账（except: pass）"，落账抛=无痕重置（比没落更坏：账上查不到
        谁在何时清了哪三把锁）。新序下落账失败时锁**根本没清**，直接 return ok=False
        且禁静默（stdout 有声+返回值指明需人工）——这与"不能因落账失败回滚已清的锁"
        不冲突：账提到清锁之前，本就不存在要回滚的已清锁；出口语义变成"本次重置未完成、
        请重试或人工"，强于"锁清了却没账"。三清本身是纯 dict 操作（不会失败）。

        v0.3 件二（plan-d2-v03 §件二，十六轮三改）：治"解锁通道随审计链挂死"——M3 正序下
        _audit 挂=三锁永远解不开，与 P-B"死锁爸爸也救不回"初衷相冲。force=True
        倒序：不问账，直接三清（出口优先），再试落 desk_state_reset（带 forced:true）；
        触发面=force 路**任一环节**（清锁抛/落账抛/部分成功同入兜底），死信行含
        stage/cleared/forced_reset/ts+清前三锁计数，位置 mia_home/runtime/
        bypass_deadletter.jsonl（与主账分离，目录不存在首写自建；无轮转+单行一次
        写入）；死信写失败也吞（print 直出）→ 返回恒为 ok/forced/deadletter，
        ok=True 无条件。二次确认=请求体 force 字段（无 settings 键，L26 不破；
        前端按钮两步式后置）。"""
        if not tid:
            return {"ok": False, "reason": "reset_thread 需要真 thread_id（? 桶不连坐）"}
        # (1) 只算不删（peek）：三把锁各自的命中数
        freeze = sum(1 for g in cls._GATE_INSTANCES if tid in (g._guard_lock or {}))
        n_over = sum(1 for g in cls._GATE_INSTANCES
                     if tid in (getattr(g, "_over_budget", None) or {}))
        n_abs = sum(1 for g in cls._GATE_INSTANCES
                    if tid in (getattr(g, "_abs_blocked", None) or {}))
        budget_detail = {"over_budget": n_over, "abs_blocked": n_abs}
        # 钉在否用裸成员判定（_pin_alive 会惰性撤钉并另落 ttl 账，此处只报现状不做事）
        _pv = cls._PRESSURE_PIN.get(tid)
        pressure = 1 if _pv is not None else 0
        _pin_id = _pv[1] if _pv else ""  # d2v03fix3⑤：desk_state_reset 账带 pin_id（reset 路）
        # (1f) v0.3 件二 force 倒序：先清后账（出口优先，账降为尽力+死信兜底）。
        # 计数 peek 在清之前算好——成功账、死信行、返回帧三处共用同一份快照。
        if force:
            # 计数 peek 已在 (1f) 之前算好——成功账、死信行、返回帧三处共用同一份
            # **清前三锁**快照（清锁抛的死信若记"清后"，半清态下就是假账）。
            _snap = {"freeze": freeze, "budget": n_over + n_abs,
                     "budget_detail": budget_detail, "pressure": pressure}
            _stage = "clear_locks"
            try:
                cls._clear_three_locks(tid)
                # 触发面扩（十六轮裁决②）：清锁与落账同入本 try——原只包落账，
                # 清锁抛=既无前置账又无兜底（force 出口反而比正序更脆，方向倒了）。
                _stage = "audit"
                import approvals as _ap
                _ap._audit("desk_state_reset", thread_id=tid, by="admin",
                           forced=True, **_snap,
                           **({"pin_id": _pin_id} if pressure else {}))
                return {"ok": True, "forced": True, **_snap}
            except Exception as _e:
                print(f"[gate] desk_state_reset force 帧异常（stage={_stage}，"
                      f"三锁快照为清前计数）：tid={tid} err={type(_e).__name__}", flush=True)
                cls._deadletter_dump(tid, _snap, type(_e).__name__,
                                     stage=_stage, cleared=(_stage != "clear_locks"))
                # ok=True 无条件：force 的语义就是"无论如何要出口"，任何环节失败
                # 都转死信出声，绝不反杀成 ok=False（那等于把旁路通道又焊死）。
                return {"ok": True, "forced": True, "audit": "deadletter"}
        # (2) 先落账（P-B：必须落账——所以账只能在动手之前落）
        try:
            import approvals as _ap
            _ap._audit("desk_state_reset", thread_id=tid, by="admin",
                       freeze=freeze, budget=n_over + n_abs,
                       budget_detail=budget_detail, pressure=pressure,
                       **({"pin_id": _pin_id} if pressure else {}))
        except Exception as _e:
            # (3) 落账失败禁静默：三锁原样未清，出声+返回未完成（调用方据此重试/转人工）
            print(f"[gate] desk_state_reset 落账失败（三锁未清，需人工处理）：tid={tid} "
                  f"err={type(_e).__name__}", flush=True)
            return {"ok": False, "reason": "落账失败，三锁未清（P-B：必须落账）"}
        # (4) 落账成功后三清（v0.3 件二：动作抽 _clear_three_locks 单一真源，
        # 与 force 帧共用一把扫帚——纯 dict 操作，不会再失败；guard_unlock 仍是冻结锁真源）
        cls._clear_three_locks(tid)
        # (5) 出口计数（口径与账上完全一致：先算后清，算的就是清掉的）
        return {"ok": True, "freeze": freeze, "budget": n_over + n_abs,
                "budget_detail": budget_detail, "pressure": pressure}

    @classmethod
    def _route(cls, name: str, args: dict | None) -> str:
        """三态映射（Cora 一行映射修双源）：pass | ask | to_deny。
        判定只活在现役 _decision 一处——本函数零判定逻辑。"""
        dec = cls._proxy_of()._decision(name, cls.read_level(), args)
        return {"pass": "pass", "selflock": "to_deny", "deny": "to_deny", "ask": "ask"}[dec]

    # ---- 官方 interrupt_on 的 when 谓词（弹卡开关）+ r41 网关批准卡预算 ----
    # hy4 R41 修正版：幂等计数/批准直通/告警上卡面/NO-TID 隔离（详见 approvals r41 段注释）
    @staticmethod
    def _tid() -> str:
        try:
            from langgraph.config import get_config
            return str((get_config().get("configurable") or {}).get("thread_id", "") or "")
        except Exception:
            return ""

    def _make_when(self, name: str):
        def when(req) -> bool:
            import approvals as _ap
            dec = self._route(name, (req.tool_call or {}).get("args"))
            if dec != "ask":
                return False
            tc_id = self._tc_key(req.tool_call or {})  # r61e Cora N3：空 id 退参数指纹
            tid = self._tid()
            gk = tid or "?"
            # r60 机器安全门（米娅版 Mimosa）：裁判独立于米娅的脑子（防注入路径）。
            # high=强制拦（连卡都不弹，不给被注入者求盖章的机会）；
            # mid=放行到批准卡但机器意见上卡面（爸爸扣章看得见风险点，NOVA/Eve 案）。
            try:
                from mia_agent.guard_scan import scan_tool, rule_ids
                _g = scan_tool(name, (req.tool_call or {}).get("args") or {})
                if _g["level"] == "high":
                    # r61（hy4 A-3）：high 命中落账（误杀率可算+注入换写法可见）+滑动窗计数
                    # r61f E18（hy4 五轮记档）：fp=无盐 sha256(args)[:12]——args 空间小
                    # 理论可枚举反推，本账接受此代价（换"同参重撞可见"的审计价值）；
                    # 下一个读账的人别把它当密码学强度。
                    import approvals as _ap2
                    import hashlib as _h0
                    _ap2._audit("guard_high", thread_id=tid, tool=name,
                                fp=_h0.sha256(str((req.tool_call or {}).get("args") or "")
                                              .encode("utf-8", "replace")).hexdigest()[:12])
                    # d2v03fix3③（Cora④）：滑窗推进→freeze_n 累加→锁写入→hits 写入
                    # 整段是读-改-写，双线程同 gk 会丢档（freeze_n get+1 非原子）——入闸。
                    with self._GATE_LOCK:
                        st = self._guard_streak.setdefault(gk, [])
                        st.append(__import__("time").time())
                        while st and st[0] < __import__("time").time() - 300:
                            st.pop(0)
                        # r61b P1-2（hy4）：只有真 tid 才配冻结（"? 桶共享"案已修）。
                        # r61e（NOVA ①）：TTL 退避 30min×2^N（30m→1h→2h），累计 3 次=永久锁
                        # 等 /approvals/guard_unlock——否则 DoS 者按"每 TTL 两发"的节奏慢慢磨，
                        # 锁线程从保险丝退化成速率限制器。
                        if len(st) >= 2 and tid:
                            n = self._guard_freeze_n[tid] = self._guard_freeze_n.get(tid, 0) + 1
                            ttl = float("inf") if n >= 3 else 1800.0 * (2 ** (n - 1))
                            self._guard_lock[tid] = (__import__("time").time(), ttl)
                            print(f"[gate] guard_lock 冻结线程 {tid[:8]}（第{n}次，ttl={ttl}）", flush=True)
                        self._guard_deny.setdefault(gk, set()).add(tc_id)
                        self._guard_hits[gk] = _g["findings"]
                    return False
                if _g["level"] == "mid":
                    with self._GATE_LOCK:  # d2v03fix3③：mid 命中缓存写入同闸
                        self._guard_mid.setdefault(gk, {})[tc_id] = _g["findings"]
                    # r61（Cora：误杀也带反馈环）mid 命中落账 ev=guard_mid。
                    # r61e（Cora N4+NOVA 六通道法）：账本=米娅可 grep 的模型可读面——
                    # why 人话改存规则 ID（稳定短哈希），人话只留卡面渲染层。
                    try:
                        import approvals as _ap3
                        import hashlib as _h1
                        _ap3._audit("guard_mid", thread_id=tid, tool=name,
                                    n=len(_g["findings"]),
                                    rids=rule_ids(_g["findings"][:3]),
                                    fp=_h1.sha256(str((req.tool_call or {}).get("args") or "")
                                                  .encode("utf-8", "replace")).hexdigest()[:12])
                    except Exception:
                        pass
                if _g.get("unknown") and name not in self._unknown_seen:
                    # r61b P2-6（hy4）：未登记进规则面的工具名=门对它零覆盖——
                    # 每个只落一次 guard_unknown 账（新增 shell/派活类工具靠这本账现形）
                    self._unknown_seen.add(name)
                    try:
                        import approvals as _ap4
                        _ap4._audit("guard_unknown", thread_id=tid, tool=name)
                    except Exception:
                        pass
            except Exception as _ge:
                # r61e（Cora N2+NOVA P0-1 哲学层）：**门崩溃≠放行**——"让守卫崩溃"
                # 本身就是攻击向量（超长回溯/编码炸弹）。三种死法（内部异常/import 失败/
                # 任何代码错误）一律 fail-closed：拒本调用+落 guard_crash 账（只存异常
                # 类名不带消息，六通道脱敏）。静默 fail-open=双倍失败（门没了+没人知道）。
                print(f"[gate] guard_scan 崩溃（fail-closed 拒本次调用）：{type(_ge).__name__}", flush=True)
                try:
                    import approvals as _ap5
                    _ap5._audit("guard_crash", thread_id=tid, tool=name, err=type(_ge).__name__)
                    self._guard_deny.setdefault(gk, set()).add(tc_id)
                except Exception:
                    pass
                return False
            # r61b P0-4（hy4）：when=False 只等于"不弹卡"，不等于"拦"——冻结语义
            # 必须落进 _check_budget_gate（见该方法冻结拒信），这里提前 return False
            # 让 wrap 层出拒信。r61c 边界C：冻结判定抽 _frozen() 双处共用
            # （TTL 推进不再依赖 when 先到）。
            if self._frozen(tid):
                # r61h P-1（hy4 八轮 E19-1）：排除出卡的 tc 同步记进不依赖 TTL 的
                # 集合——wrap 先消费它出拒信；即使 when→wrap 之间锁恰好 TTL 到期
                # （_frozen 变 False、又不在 _guard_deny），也不会走到"直接执行"。
                self._frozen_hold.setdefault(gk, set()).add(tc_id)
                return False
            # r46（Veda 治本炮+09-13 C1#3 复发实证）：execute 的数据区绝对路径形式
            # （/notes /memory /knowledge）与全盘 find=已知坑源，机械判参直接不弹卡
            # （预算不烧、卡不弹，拒信教正确写法）——说明书文案两次实证不够。
            if name == "execute":
                try:
                    from mia_agent.acceptance_kit import check_path_form
                    bad = check_path_form(str((req.tool_call or {}).get("args", {})
                                              .get("command", "") or ""))
                    if bad or _FULLFIND.search(str((req.tool_call or {}).get("args", {})
                                                   .get("command", "") or "")):
                        self._abs_blocked.setdefault(tid, set()).add(tc_id)
                        return False
                except Exception as _e:
                    print(f"[gate] 路径形态断言失败放行：{_e}", flush=True)
            if not tid:
                # hy4 P0-1：无 tid 不进任何共享桶——独立小桶（等于不耗预算），卡照弹，
                # 人是最后闸；绝不允许一个上下文烧光全站额度（r25 随机桶同款教训）。
                return True
            tc = req.tool_call or {}
            # r49 双钮：命中"批准并记住这类"规则→免卡（when=False=不 interrupt 直接放行；
            # 首版写成 return True=弹卡——when 语义反向事故，03:xx 已修）
            try:
                import hashlib as _hl2
                from settings_mgr import load_settings
                from mia_agent import remember_rules as _rr
                if _rr.hit(name, tc.get("args") or {}, load_settings()):
                    _ap._audit("rule_pass", tid, name,
                               fp=_hl2.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12])
                    return False
            except Exception as _re:
                print(f"[gate] remember_rules 查询失败（放行走正常门）：{_re}", flush=True)
            import hashlib as _hl
            _fpv = _hl.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12]
            _ap.bump_blocked(tid, tc_id, fp=_fpv)  # (tid,tc_id) 幂等：resume 不双计；r43 空 id 退参数指纹（hy4 P1-1）
            # r2-2：软轨告警计数已随 bump_blocked 同点递增（幂等保护在其内部），
            # 卡面告警文案另受 note_new_turn 按轮清零（见 after_model）。
            # r32b 退役（爸爸 09-26 裁决）：批准卡硬预算整体退役——"满 8 张拒弹"曾把
            # 长任务拦腰截断（miafirm 接入第 9 张卡被拒=干到一半被迫停工汇报；
            # 爸爸原话"也没看 zcode 给你放批准卡限额啊"）。爸爸在线逐卡批=人就是预算；
            # 计数照记（卡面软提醒+账本）。牛马不受影响：子层 SubGate 不走本路径（不弹卡），
            # 它们的配额是任务侧返工轮次（tasks.py），两套账本本就该分开。
            # _over_budget 集合与 wrap 层精准拒保留：管理端重置入口/外部登记/在途清理不受影响。
            return True
        return when

    def __init__(self, sub_mode: bool = False, **kw: Any):
        # r61b（hy4 P1-1 闭环）：类级实例登记——office 端点 /approvals/guard_unlock
        # 与 gate 同进程（单 uvicorn），靠这本花名册触达活实例的 _guard_lock。
        ConfirmGateC1._GATE_INSTANCES.append(self)
        # 反选架构下名单在 after_model 动态补全；初始空表。
        self.sub_mode = sub_mode
        self._over_budget: dict = {}  # {tid: set(tool_call_id)} 预算扣卡的调用（wrap 精准拒）
        self._clarify: dict = {}      # {tid: bool} r44b：task_brief 待澄清态（卡面提示用）
        self._abs_blocked: dict = {}  # {tid: set(tc_id)} r46 路径形态门扣卡的调用
        # r61h P-1（hy4 八轮 E19-1）：when 判冻结排除出卡的 tc_id 登记处——
        # {tid或?: set(tc_id)}，**不依赖 TTL**：wrap 先消费它出拒信，堵
        # "when→wrap 之间锁恰好到期"的窄竞态 fail-open（敞怀执行）。
        self._frozen_hold: dict = {}
        self._shown_seen: set = set()  # r49 {(tid,fp)} card_shown 幂等集
        self._guard_deny: dict = {}   # r60 {tid: set(tc_id)} 机器门 high 强制拦
        # intentionally NOT cleared by reset：被拒 tc_id 防重放（消费链见 _deny 命中分支——
        # 行号不钉死，09-16 二十轮 hy3④：L656 已漂至 L694，注释只描述紧邻真源），清=安全特性回退
        # （d2v03fix3② Cora 判词：reset 不该复活被拒的调用——这是设计不是遗漏；
        #  _clear_three_locks 清 freeze_n/mid/hits 三件而独留此件。）
        self._guard_hits: dict = {}   # r60 {tid: findings} 最近 high 命中（落账用）
        self._guard_mid: dict = {}    # r60 {tid: {tc_id: findings}} 中危上卡面
        # r61（Cora：锁粒度=线程不是全局。锁全局=被注入线程连环触 high 拿门
        # 当武器瘫痪全家（DoS via guard）；锁线程则攻击半径=单线程，别的活照干）
        self._guard_streak: dict = {}  # {tid: [ts,...]} 5 分钟滑窗 high 计数
        # r61b P1-1（hy4）：锁带 TTL 自愈；r61e（NOVA ①）：{tid:(ts,ttl)} 且 TTL 按
        # 冻结次数指数退避 30m→1h→2h，第 3 次=永久（防"每 TTL 两发"磨锁），
        # 出口=/approvals/guard_unlock（已上线）。解封落账 guard_ttl_release 不静默。
        self._guard_lock: dict = {}    # 冻结线程 {tid: (冻结时刻, ttl秒)}
        self._guard_freeze_n: dict = {}  # {tid: 累计冻结次数}（退避档位）
        self._unknown_seen: set = set()  # r61b P2-6：未登记工具名每个只落一次 guard_unknown
        # D2 压力降档：与 _guard_streak **分账独立**——那个数 high 命中滑窗（冻结链），
        # 这个数一切 error 态连续失败（工具 error/门拒信/异常崩溃各计 1，成功清零）。
        # D2 四件②：两只 dict 已上提类级声明（见类头 _PRESSURE_PIN 旁），此处不再实例化。
        super().__init__(interrupt_on={}, **kw)
        # r61d 边界A 断言（hy4 P2-10）→ r61h B-6 真值域改写 → P-A 收窄版（爸爸 09-14 夜
        # 裁定，plan-deskcontrol-v03 第四节第 5 条；工程笔记 eng-log R10.106 补记）→
        # **本单（09-14 续）：full 档豁免**。非 full 档时 execute 永不允许静默 pass
        # （判到即 raise=起不来，不许带病上线）；write_file/edit_file 路由到 pass=auto_edit
        # 档 _SOFTWRITE 设计路径（四档自由选择是政令），不再 raise。
        # full 豁免的出处=本单实核 P0：full 档 _decision 全工具 pass（confirm_gate L103），
        # 旧断言下按 full=服务必起不来——断言从保险丝退化成档套，选档即事故。
        # 豁免≠不设防（政令：绝对红线+同档）：full="不请示"，拒是机制不是请示——
        # pass 路跳检洞（when 在 `dec != "ask"` 短路，guard_scan 零覆盖，09-14 实核真洞）
        # 由 _check_budget_gate 的 pass 分支内容门扩到 execute 兜住（high 拒+落账，
        # mid/low 按档义放行）。
        if not sub_mode and self.read_level() != "full":
            for _t in ("execute",):
                try:
                    _d = self._route(_t, {})
                except Exception:
                    continue  # 路由表未就绪（装配早期）不炸，真判到 pass 才炸
                if _d not in ("ask", "to_deny"):
                    raise RuntimeError(f"guard coverage broken: {_t} routed to pass")

    def _budget_refusal(self, name: str) -> str:
        return (f"⛔ 「{name}」被网关预算拦下：本任务批准卡配额已用完（拦一次计一次，换参数也计）。"
                "停下——把目标、已完成步骤、卡在哪三件事向爸爸汇报；"
                "爸爸可在新对话里重开额度，或在管理端重置本任务预算。不许再试探性调用。")

    def _freeze_refusal(self, tid: str = "") -> str:
        # r61h P-1（hy4 八轮）：冻结拒信抽文案真源（同 _budget_refusal 惯例）——
        # _frozen 直判分支与 _frozen_hold 接力分支共用，防两处各写一份后漂移。
        # r61h 九轮 N-4（hy4 九轮）：解除时限不再硬编码"30 分钟"（与 r61e 指数退避
        # 不符）——读 _guard_lock 里的退避真值（when 侧 1800×2^(n-1)、n≥3=inf 唯一
        # 写点，此处只换算不再立第二套常量）；永久锁指向 /approvals/guard_unlock 出口。
        base = ("⛔ 本线程已被机器安全门冻结：短时间内连续命中高危形态，门已停止一切"
                "审批交互等待爸爸接管。请停止调用工具，把本线程目标与最近尝试的操作"
                "向爸爸汇报。")
        lock = self._guard_lock.get(tid or "")
        if lock and lock[1] == float("inf"):
            return base + ("本锁为永久冻结（累计第 3 次，退避已到顶），不再自动解除——"
                           "需爸爸在管理端 /approvals/guard_unlock 解冻，本线程方可继续。")
        if lock:
            import math
            _m = max(1, math.ceil((lock[1] - (__import__("time").time() - lock[0])) / 60))
            _span = f"{_m // 60} 小时" if _m >= 60 and _m % 60 == 0 else f"{_m} 分钟"
            return base + f"冻结约 {_span}后自动解除。"
        # hy4 十轮 N-4：兜底档不再枚举具体档位（30m→1h→2h→永久）——档位常量若漂移，
        # 写死的枚举就成了谎话；只说实话，真值以 when 侧写点（guard 退避）为准。
        return base + ("冻结按退避策略自动解除（具体档位见 guard 退避真值）；"
                       "若为永久锁，需爸爸在管理端 /approvals/guard_unlock 解冻。")

    @staticmethod
    def _tc_key(tc: dict) -> str:
        """r61e（Cora N3）：tc_id 空值退参数指纹——r43 bump_blocked 同款教训复用，
        防所有无 id 调用共享空串键（一个被拒全体连坐/一个登记全体免卡）。"""
        _id = str(tc.get("id") or "")
        if _id:
            return _id
        import hashlib as _h
        return "fp:" + _h.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12]

    def _process_decision(self, decision, tool_call, config):
        """r61e 审计缺口修复（Nova 1.3.18 活体验证方案；Veda 批次明细口径；
        Eve 结构性事实：官方件 approve/edit 消费无痕，只有 reject/respond 留 ToolMessage）。
        覆写消费点钩子：批量卡经 resume decisions 逐条过这里——先落账再交官方件
        （审计先于动作，非法 decision 抛错前也留痕）。父类是 staticmethod、调用点
        self._process_decision → 实例方法覆写可拿到 tid。
        ⚠ 版本钉（Nova）：私有方法签名跨小版本可能变——升级 langchain 必跑
        tools/test_c1_hook.py（喂 approve/edit 断言钩子触发+官方语义不扰）。"""
        try:
            import approvals as _ap
            # r61h P-1（hy4 八轮 附带案）：无 tid 归一记 "?"——与"真 tid 缺失"区分
            # （旧版记空串与 _audit 默认值同形，读账分不出来；? 桶语义同 r61c N1）。
            _ap._audit("c1_decision", thread_id=self._tid() or "?",
                       tool=str((tool_call or {}).get("name", "")),
                       dtype=str((decision or {}).get("type", "?")),
                       edited=bool((decision or {}).get("edited_action")),
                       reason=str((decision or {}).get("message", ""))[:80])
        except Exception:
            pass  # 落账失败不挡批准主链（批准语义优先，缺账由对账脚本兜底补）
        # D2 压力降档解除：approve/edit=爸爸放行一次 → 清零+撤钉（reject 不是放行）。
        if str((decision or {}).get("type", "")) in ("approve", "edit"):
            self._pressure_release(self._tid())
        return HumanInTheLoopMiddleware._process_decision(decision, tool_call, config)

    def _frozen(self, tid: str) -> bool:
        """r61c 边界C（hy4）：冻结判定单一函数（when 与 wrap 共用，TTL 只此一处推进）。
        N20：TTL 到期时把 deny/hits/streak 一并清，不留只增集合。
        r61e（NOVA ①）：解封不静默——落账 guard_ttl_release（爸爸要能看到
        "刚解封一个冻过 N 次的线程"）；永久锁（ttl=inf）只能走 guard_unlock 端点。"""
        if not tid or tid not in self._guard_lock:
            return False
        ts, ttl = self._guard_lock[tid]
        if __import__("time").time() - ts > ttl:
            self._guard_lock.pop(tid, None)
            self._guard_streak.pop(tid, None)
            self._guard_deny.pop(tid, None)
            self._guard_hits.pop(tid, None)
            _n = self._guard_freeze_n.get(tid, 0)
            try:
                import approvals as _apx
                _apx._audit("guard_ttl_release", thread_id=tid, n=_n)
            except Exception:
                pass
            print(f"[gate] guard_lock TTL 解封 {tid[:8]}（第{_n}次冻结到期）", flush=True)
            return False
        return True

    def _check_budget_gate(self, request):
        """wrap/awrap 共用：返回 ToolMessage=拒；None=放行。"""
        import approvals as _ap
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", ""))
        args = tc.get("args")
        dec = self._route(name, args)
        if dec == "to_deny":
            kind = "selflock" if ConfirmGateMiddleware._path_locked(name, args) else "deny"
            return ToolMessage(
                content=self._proxy_of()._block_msg(name, self.read_level(), kind, args),
                tool_call_id=tc.get("id", ""),
            )
        tid = self._tid()
        # r61c N1（hy4 二轮 P0）：when 侧写键 `tid or "?"`、本侧读裸 tid——无 tid
        # 线程的 high 既不弹卡也读不到 deny=**敞怀放行**。键归一 `gk` 单一真源。
        # r61e（Cora N3 连锁自审）：when 侧 tc_id 已改指纹键（_tc_key），本侧读必须
        # 同步——否则空 id 调用写读错配=登记了拒信读不到。r61h P-1：gk/tck 上提到
        # 取 tid 后即算——紧随其后的冻结接力集合也用同一对键做读写。
        gk = tid or "?"
        tck = self._tc_key(tc)
        # r61h P-1（hy4 八轮 E19-1）："when 判冻结排除出卡 → wrap 兜拒信" 的接力链
        # ——wrap 先消费不依赖 TTL 的登记集合 _frozen_hold：即使 when→wrap 之间锁
        # 恰好到期（_frozen 已 False、又不在 _guard_deny），冻结 tc 仍吃拒信不执行。
        if tck in (self._frozen_hold.get(gk) or set()):
            self._frozen_hold[gk].discard(tck)
            return ToolMessage(content=self._freeze_refusal(tid), tool_call_id=tc.get("id", ""))
        # r61b P0-4（hy4 命门）：when=False 只等于"不弹卡"，不等于"拦"——wrap 层不出拒信的话，
        # 被冻结线程的一切 ask 调用=自动放行（攻击者故意连撞 2 次 high 即换取
        # 免审批执行，攻击方向与设计相反）。冻结态 ask 一律回冻结拒信；
        # P1-3：文案与预算拒/机器 high 拒区分——爸爸一眼分清"接管解冻"还是"重开额度"。
        if dec == "ask" and self._frozen(tid):
            return ToolMessage(content=self._freeze_refusal(tid), tool_call_id=tc.get("id", ""))
        # r60 机器门 high：强制拦。
        # r61 拒信改造（hy4 A-4 脱敏 + Eve 正向出口 + Veda 撤"不要绕行"句）：
        # ①findings 细节不进模型拒信（只进 guard_high 账本+卡面）——拒信含命中
        #   关键词=给注入者的教材（告诉它门在看什么，改写法即绕）；
        # ②撤"不要换写法绕行"负向句——对被改写目标函数的模型无效，反而提示
        #   "换写法"这个选项存在。给正向出口：W2 实证"给她出口她就走出口"。
        if tck in (self._guard_deny.get(gk) or set()):
            self._guard_deny[gk].discard(tck)
            return ToolMessage(content=(
                "⛔ 机器安全门拦截：该调用形态被确定性规则拦截，此级别不进入批准流程，"
                "本调用不可重试。若任务确需完成该类操作，请改用 write_file/edit_file 等"
                "白名单工具达成目标，或把目标与替代方案向爸爸汇报，由爸爸定夺。"),
                tool_call_id=tc.get("id", ""))
        if dec == "ask" and tck in (self._over_budget.get(tid) or set()):
            self._over_budget[tid].discard(tck)  # 消费一次，防集合膨胀
            return ToolMessage(content=self._budget_refusal(name), tool_call_id=tc.get("id", ""))
        if dec == "ask" and tck in (self._abs_blocked.get(tid) or set()):
            self._abs_blocked[tid].discard(tck)
            # r46（Veda 炮落地）：绝对形式硬拒——拒信即教学（不烧预算不弹卡）
            return ToolMessage(content=(
                f"⛔ execute 命令被路径形态门拦下：命令里出现了 /notes 等数据区绝对路径"
                f"或全盘 find。你的 shell 工作目录就是数据区根——**一律写相对路径"
                f"（notes/…），永远不要以 / 开头**。用相对路径重发同一命令即可。"),
                tool_call_id=tc.get("id", ""))
        # r61h P-A 收窄（爸爸 09-14 夜裁定，plan-deskcontrol-v03 第四节第 5 条；工程笔记
        # eng-log R10.106 补记）→ 09-14 续单扩到 execute：write/edit 的 pass=auto_edit 档
        # _SOFTWRITE 设计路径、execute 的 pass=full 档档义（full=不请示≠不设防，政令
        # "绝对红线+同档"：拒是机制不是请示，不违"不问"语义）。启动断言已不再按故障 raise
        #（见 __init__）——但收窄不许开洞：when 侧在 `dec != "ask"` 处短路，pass 路由
        # guard_scan 零覆盖（09-14 实核：pass 即跳检，真洞）。wrap 层每次调用必过
        #（Eve 架构事实），内容门在此无条件补跑：high（私钥字面量/后门直投路径/rm 根与
        # 系统目录类破坏命令）一律拒+落 guard_high 账——与 when 侧同口径"不给被注入者
        # 求盖章的机会"（无卡档本就没有可求的章）；mid/low 放行（mid 在 ask 路径只是
        # 上卡面意见，无卡档=爸爸选档时已接受的语义，拒=日常操作全变误杀，
        # Eve P1-A"guard 自伤停工"教训）。扫描崩溃=拒（fail-closed，r61e Cora N2 同案，
        # execute 侧与 write 侧同规格）。冻结/滑窗链仍留在 when 侧：本路径不弹卡，
        # 不存在"磨卡"攻击面，不重复建。
        # 09-14 续单第二弹（P-A 扩面，工兵实核）：full 档 _decision 全工具 pass，
        # delete/派活三手/edit_memory 原在 pass 路零扫描直过=敞口——名单扩入。
        # 扫描入参按各工具 args 形态适配到既有通道（guard_scan 一字不改）：
        # delete 的 file_path 走写侧后门路径规则（_BACKDOOR_PATHS，删 .ssh/、etc/
        # 与投 .ssh/ 同罪）；edit_memory 的 content 走写侧内容规则（无路径目标，
        # file_pattern ".*" 的通用规则照常命中——私钥字面量 high）；
        # dispatch_to_xiaoquan/dispatch_external/start_async_task 与 guard_scan
        # 既有 dispatch 通道（task/description 文本）原生同名，直传。
        # mcp__* 动态名本轮不扩（待政令）。
        if dec == "pass" and name in ("write_file", "edit_file", "execute",
                                      "delete", "edit_memory",
                                      "dispatch_to_xiaoquan", "dispatch_external",
                                      "start_async_task"):
            sn, sa = name, (args or {})
            if name == "delete":
                sn, sa = "write_file", {"file_path": str((args or {}).get("file_path") or "")}
            elif name == "edit_memory":
                sn, sa = "write_file", {"file_path": "",
                                        "content": str((args or {}).get("content") or "")}
            try:
                from mia_agent.guard_scan import scan_tool
                _g = scan_tool(sn, sa)
            except Exception as _ge:
                print(f"[gate] pass 路由 guard_scan 崩溃（fail-closed 拒本次调用）：{type(_ge).__name__}", flush=True)
                try:
                    _ap._audit("guard_crash", thread_id=tid, tool=name, err=type(_ge).__name__)
                except Exception:
                    pass
                return ToolMessage(content=(
                    "⛔ 机器安全门拦截：内容扫描异常（fail-closed），本次调用未执行。"
                    "停止并把本线程目标向爸爸汇报。"), tool_call_id=tc.get("id", ""))
            if _g["level"] == "high":
                try:  # 落账与 when 侧同规格（guard_high+fp；D-1 挂账的无盐指纹代价同案）
                    import hashlib as _h9
                    _ap._audit("guard_high", thread_id=tid, tool=name,
                               fp=_h9.sha256(str(args or "").encode("utf-8", "replace")).hexdigest()[:12])
                except Exception:
                    pass
                return ToolMessage(content=(
                    "⛔ 机器安全门拦截：本次写入/命令的内容或目标命中确定性高危形态，"
                    "此级别不进入批准流程，本调用不可重试。请把目标与替代方案向爸爸"
                    "汇报，由爸爸定夺。"), tool_call_id=tc.get("id", ""))
        return None

    # ---- D2 压力降档（plan-d2-pressure-v1，09-15 爸爸批 N=3）----
    # 机器可判的"她不会吭声"（METR 0/1300）：连败≥N → 钉 strict+落账+下一次拒信/
    # 卡面附一行告知——不给模型"要不要继续试"的裁量。口径只数机器可判 error 态，
    # 不读"模型自我怀疑"（规格边界：不自作主张清单）。

    @staticmethod
    def _pressure_n() -> int:
        """阈值 N=settings 顶层键 desk_pressure_n，缺省/非法回 3（爸爸拍板值）。
        本单不写配置文件——要调是设置页侧的事（L26 唯一入口不破）。"""
        try:
            from settings_mgr import load_settings
            v = int((load_settings() or {}).get("desk_pressure_n", 3))
            return v if v >= 1 else 3
        except Exception:
            return 3

    @staticmethod
    def _result_is_error(result) -> bool:
        """error 态判定：ToolMessage status=error；Command 等复合结构翻 update.messages。
        其余结构按成功对待——规格只钉"成功清零"，不发明第四种失败。"""
        def _scan(obj) -> bool:
            if isinstance(obj, ToolMessage):
                return str(getattr(obj, "status", "") or "") == "error"
            upd = getattr(obj, "update", None)
            if isinstance(upd, dict):
                return any(_scan(m) for m in (upd.get("messages") or []))
            return False
        return _scan(result)

    def _pressure_release(self, tid: str) -> None:
        """解除（批准卡放行路径）：连败清零+撤钉+未送出的告知作废（档都撤了，
        降档告知再送就是谎话）。成功调用只清计数不清钉——撤钉只认爸爸放行或新线程。
        真撤钉落账 desk_pressure_release（hy4 新 N1：钉有 downgrade 账、撤却无声=
        半本账，读账人判不了"这线程现在还钉着吗"，误杀率算不了）。
        d2v03fix3⑤：批准撤钉账带 pin_id（release 三路之一）。
        d2v03fix3③：弹出与 _note_fail 攒数/when 侧判定互斥——入闸。"""
        gk = tid or "?"
        with self._GATE_LOCK:
            self._fail_streak.pop(gk, None)  # 整只 st 弹出=n/recent/fired 一并清零
            self._pressure_notice.pop(gk, None)
            _pv = ConfirmGateC1._PRESSURE_PIN.pop(tid, None) if tid else None
            if _pv is not None:
                try:
                    import approvals as _ap
                    _ap._audit("desk_pressure_release", thread_id=tid,
                               **({"pin_id": _pv[1]} if _pv[1] else {}))
                except Exception:
                    pass  # 落账失败不挡放行主链（同 _process_decision 口径）

    def _pressure_fire(self, gk: str, st: dict) -> None:
        """连败达阈触发一轮一次（fired 旗防同段重复，判据见 _note_fail）。三件套：
        降档（仅真 tid 且真源非 strict/plan）、落账、告知登记（实际附送去见
        _attach_pressure/_make_desc）。level_and_source 套 try（hy4 十二轮补法可选
        加固，采纳）：读档失败=不钉但照落账+另记 desk_pressure_readfail——记账钩子
        绝不反杀主链（P-C 案：设置页重写窗口内 _level 二次读可抛）。
        上沿账（d2v03fix3④⑤ Cora①②）：本帧真落钉 → 账带 pin_set:1+pin_id；
        残余帧（downgraded=False 且 src=="pin"，钉已在位）同样带 pin_set:1+同一
        pin_id——"钉落下无痕"就此闭合，按 pin_id 单查询可追一颗钉的一生。
        d2v03fix3③：判定→落钉是读-改-写（与 _pin_alive 到期自清竞态可双落），入闸。"""
        tid = "" if gk == "?" else gk
        # level_and_source 已含既有钉：二轮连败（放行清零后再攒满）视角=strict 且
        # src="pin"——幂等不重写钉，账加 pin:1（v0.3 件四折中案，十六轮裁决④：
        # 两维正交，"level+downgraded 组合判"不认；仅 src=="pin" 时账带 pin:1，
        # 常态新触发帧（此刻 src=="true"）零膨胀、钉下再触发帧可判）。
        downgraded = False
        lvl = ""
        src = "true"
        pin_id = ""
        with self._GATE_LOCK:
            try:
                lvl, src = self.level_and_source()
                if lvl not in ("strict", "plan") and tid:
                    _ts = __import__("time").time()
                    # d2v03fix3⑤：pin_id=钉入 ts+tid 前 4；_PRESSURE_PIN 值形 (ts, pin_id)
                    pin_id = f"{_ts:.1f}-{tid[:4]}"
                    ConfirmGateC1._PRESSURE_PIN[tid] = (_ts, pin_id)
                    downgraded = True
                elif src == "pin" and tid:
                    _pv = ConfirmGateC1._PRESSURE_PIN.get(tid)
                    pin_id = _pv[1] if _pv else ""  # 残余帧：续用既有钉的 pin_id
            except Exception as _pe:
                print(f"[gate] D2 level_and_source 失败（不钉，照落账）：{type(_pe).__name__}", flush=True)
                try:
                    import approvals as _apr
                    _apr._audit("desk_pressure_readfail", thread_id=tid or "?",
                                err=type(_pe).__name__)
                except Exception:
                    pass
        try:
            import approvals as _ap
            # level=触发瞬间读到的视角档（readfail 时为空串，与 desk_pressure_readfail
            # 对账）；downgraded 明写是否真钉——"C 档落账但没真降"自解释（hy4 新 N1）；
            # pin:1 仅在档由活钉撑起时出现（缺键=与旧账同形，读账侧 `"pin" in rec` 判）；
            # pin_set:1=此帧在钉中/落钉（真落帧与残余帧皆带，Cora①上沿账）；
            # pin_id 随 pin_set 帧出现（一颗钉的一生单查询）。
            _ap._audit("desk_pressure_downgrade", thread_id=tid or "?",
                       streak=st["n"], fails=list(st["recent"]),
                       downgraded=downgraded, level=lvl,
                       **({"pin": 1} if src == "pin" else {}),
                       **({"pin_set": 1} if (downgraded or src == "pin") else {}),
                       **({"pin_id": pin_id} if pin_id else {}))
        except Exception:
            pass  # 落账失败不挡主链（同 _process_decision 口径）
        head = f"⚠ 已连续失败 {st['n']} 次"
        # hy4 十三轮卫生批①：原两分支以 downgraded 单一判据分岔——readfail 帧（lvl=""）
        # 也落进"当前已是变更前确认/计划档"，那是**断言了一个没读到的档位**（断言式谎话，
        # 不是措辞不准）。按 downgraded/lvl 拆三支："已在高档"的判据改回读到的 lvl 本身，
        # 兜底支（读档失败未敢降/无真 tid 不可跨线程降档）不报任何档位。
        if downgraded:
            line = head + "：本线程已自动降为变更前确认（strict），请爸爸复核方向。"
        elif lvl in ("strict", "plan"):
            line = head + "：当前已是变更前确认/计划档（未再降档），请爸爸复核方向。"
            # hy4 十七轮①观察项（同族同待）：钉撑帧（src=="pin"，真源仍可 auto_edit）
            # 上一句里的"当前已是…档"说的是**生效档**，话术面必须自报来源——来源只
            # 记在账面（pin:1）不够，读者看的是这句话。措辞与 SubGate._report 的
            # pinned 句逐字同规格（家规：计数与措辞口径绝不分叉），不另立第二套说法。
            if src == "pin":
                line += "（本线程临时降为变更前确认=压力降档，非设置真源变更）"
        else:
            line = head + ("：档位读取失败或本线程无法定位，本次未敢自动降档"
                           "（当前档位不明），请爸爸复核方向。")
        self._pressure_notice[gk] = line

    def _safe_note(self, request, kind: str, err: str = "") -> None:
        """D2 计数钩子的保护壳（hy4 十二轮必改①）：记账钩子绝不改主链语义——
        崩溃点靠它保证 raise 无条件可达（真异常不被 settings 侧异常顶掉，__context__
        都不该挪），拒信点靠它保证合法拒信不被钩子异常变崩溃（家规：门崩溃≠放行、
        异常链不许被吞）。"""
        try:
            self._note_fail(request, kind, err)
        except Exception as _e:
            print(f"[gate] D2 计数失败（不影响主链）：{type(_e).__name__}", flush=True)

    def _note_fail(self, request, kind: str, err: str = "") -> None:
        """一次失败计 1。摘要脱敏口径同 guard_high 账：只落 类型+工具名+参数指纹
        （sha256[:12]）+异常类名（不含消息）——args 原文/报错内容不进账
        （r61e 六通道脱敏；给模型看的拒信从不带命中词，同案）。"""
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", "?"))
        import hashlib as _h
        fp = _h.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12]
        summary = " ".join((f"{kind} {name} fp={fp}" + (f" err={err}" if err else "")).split())[:80]
        gk = self._tid() or "?"
        with self._GATE_LOCK:  # d2v03fix3③（Cora④）：setdefault→+=1→fired 判定非原子
            st = self._fail_streak.setdefault(gk, {"n": 0, "recent": [], "fired": False})
            st["n"] += 1
            # recent 只留最近 3 条：N>3 时账上证据条数 < streak（streak 是真数、证据是
            # 抽样）——读账人别拿 len(fails) 当连败数（hy4 十二轮次要项）。
            st["recent"] = (st["recent"] + [summary])[-3:]
            # fired 旗（hy4 十二轮 §3-2）：原 n==N 精确等号脆——任一帧 fire 被跳过（P-C
            # 那类）后 n 只增、== 永不复中，本轮连败再也不降档。改 n>=N 且未 fired：一轮
            # 连败只触发一次；清零（成功/批准整只 st 弹出）自然连带清 fired。
            if st["n"] >= self._pressure_n() and not st.get("fired"):
                st["fired"] = True
                self._pressure_fire(gk, st)

    def _attach_pressure(self, msg: ToolMessage) -> ToolMessage:
        """告知附送点1=拒信面（点2=批准卡面 _make_desc，共用同一只旗）。消费即清——
        只附"下一次"，不逐封刷（告知是给爸爸的，不是复读咒骂）。"""
        gk = self._tid() or "?"
        line = self._pressure_notice.pop(gk, None)
        if line:
            msg.content = f"{msg.content}\n{line}"
        return msg

    def wrap_tool_call(self, request, handler):
        """拒类出口（自包含）+预算精准拒：不赌 middleware 顺序，也不吞爸爸刚批的调用。
        D2 压力降档钩子：拒信/工具 error/崩溃各计 1，成功清零（awrap 同构）。"""
        blocked = self._check_budget_gate(request)
        if blocked is not None:
            self._safe_note(request, "refuse")
            return self._attach_pressure(blocked)
        try:
            result = handler(request)
        except Exception as e:
            self._safe_note(request, "crash", err=type(e).__name__)
            raise  # 必须在下且无条件可达（hy4 P-C）：计数钩子抛天也吞掉真异常
        if self._result_is_error(result):
            self._safe_note(request, "tool_error")
        else:
            with self._GATE_LOCK:  # d2v03fix3③：成功清零与攒数互斥（与 _note_fail 同闸）
                self._fail_streak.pop(self._tid() or "?", None)  # 成功清零（整只 st 弹出=连 fired 一并清；撤钉只认批准放行）
        return result

    async def awrap_tool_call(self, request, handler):
        """异步版（langgraph 全异步必双钩——00:14 NotImplementedError 教训）。
        D2 钩子与同步版同构（计数口径绝不分叉，awrap 唯一差异是 await）。"""
        blocked = self._check_budget_gate(request)
        if blocked is not None:
            self._safe_note(request, "refuse")
            return self._attach_pressure(blocked)
        try:
            result = await handler(request)
        except Exception as e:
            self._safe_note(request, "crash", err=type(e).__name__)
            raise  # 同步步同构：raise 无条件可达
        if self._result_is_error(result):
            self._safe_note(request, "tool_error")
        else:
            with self._GATE_LOCK:  # d2v03fix3③：与同步版逐字同构（口径绝不分叉）
                self._fail_streak.pop(self._tid() or "?", None)  # 成功清零（整只 st 弹出=连 fired 一并清）
        return result

    def _make_desc(self, name: str):
        """卡面告警接线（hy4 P1-1）：>=3 张起在批准卡描述追加压力提示——
        Eve 口径"存在要可见、数值要模糊"，不报确切张数。"""
        def desc(tool_call, state, runtime):
            import approvals as _ap
            import json as _j
            base = f"Tool execution requires approval\n\nTool: {name}\nArgs: {tool_call.get('args')}"
            tid = self._tid()
            try:
                preview = _ap.card_pressure(tid)
            except Exception:
                preview = ""
            # r60 机器门 mid：机器意见上卡面（爸爸扣章时看得见风险点，不需要他懂）
            try:
                _mid = (self._guard_mid.get(tid or "?") or {}).get(self._tc_key(tool_call or {}))
                if _mid:
                    _m = "🛡 机器扫描提示：" + "；".join(w for _, w in _mid[:3]) + "（确认无误再批）"
                    preview = (preview + "\n" + _m) if preview else _m
            except Exception:
                pass
            # D2 压力降档告知附送点2=批准卡面（与拒信侧 _attach_pressure 共一只旗，
            # 谁先见到爸爸谁消费——"下一次"承诺不双送）。
            _pl = self._pressure_notice.pop(tid or "?", None)
            if _pl:
                preview = (preview + "\n" + _pl) if preview else _pl
            if self._clarify.get(tid):  # r44b-P1-4：clarify 消费——验收目标未定就弹了卡，
                preview = (preview + "\n" if preview else "") + \
                    "📋 任务简报：本任务未从原话提到可核对的目标字面量——建议先跟爸爸确认要什么再动手（问是免费的）。"
            return (base + "\n" + preview) if preview else base
        return desc

    def after_model(self, state, runtime):
        """动态反选：把本回合出现的每个工具名（未注册的）先注册成 when 配置，
        再交官方批量流程——官方"未列名=自动放行"的 fail-open 从根堵死。
        扫描面与官方 after_model 对齐（last AI message）：官方也只对 last_ai 的
        tool_calls 求值 when，多扫无意义（hy4 P2 答复：非漏网，官方语义即单流）。
        （Eve 必测2 已解：官方 _should_interrupt 构造的 ToolCallRequest 携带完整
        tool_call 含 args——L397-402 源码可证+NOVA 本地实证，台账可装进 when。）"""
        messages = state.get("messages") or []
        # r44 层2：换任务判定挂 task_brief 目标 diff（"继续/嗯/再试"不清告警——
        # Cora/Lyra 案）；无简报线程回退 human 计数旧通道。硬预算软重置 BUDGET//2。
        tid = self._tid()
        if tid:
            import approvals as _ap
            # r44b-P1-5（hy4）：批准 nudge 注入的 role=user 消息不得参与换任务判定——
            # 统计/取"最后一条爸爸的话"时排除带 system_nudge 标记的消息。
            def _is_dad(m):
                return getattr(m, "type", "") == "human" and \
                    "system_nudge" not in (getattr(m, "additional_kwargs", None) or {})
            n_human = sum(1 for m in messages if _is_dad(m))
            last_human = next((m for m in reversed(messages) if _is_dad(m)), None)
            txt = ""
            if last_human is not None:
                c = getattr(last_human, "content", "")
                txt = c if isinstance(c, str) else str(c)
            new_task = False
            try:
                if txt:
                    from mia_agent import task_brief as _tb
                    b = _tb.note_task(txt, tid, n_human)
                    new_task = bool(b.get("new"))
                    self._clarify[tid] = bool(b.get("clarify"))  # P1-4：clarify 死字段接活
                    if b.get("clarify"):
                        _ap.note_new_turn(tid, n_human)  # 待澄清期不清硬账，仅同步轮标
            except Exception as e:
                print(f"[gate] task_brief 失败回退旧通道：{e}", flush=True)
            if new_task:
                _ap.soft_reset_task(tid)
                _ap.note_new_turn(tid, n_human)  # P2-11：换题轮同步
            elif not txt:
                _ap.note_new_turn(tid, n_human)
        last_ai = next((m for m in reversed(messages)
                        if getattr(m, "tool_calls", None)), None)
        import hashlib as _hl  # r49 批准账指纹用（本作用域独立 import，when 里的不共享）
        if last_ai:
            ask_pending = []
            for tc in last_ai.tool_calls:
                nm = str(tc.get("name", ""))
                if nm and nm not in self.interrupt_on:
                    self.interrupt_on[nm] = InterruptOnConfig(
                        allowed_decisions=["approve", "edit", "reject"],
                        when=self._make_when(nm),
                        description=self._make_desc(nm),
                    )
                if self._route(nm, tc.get("args")) == "ask":
                    ask_pending.append((nm, tc.get("args")))
                    # r49 批准账：卡面展示即事件（同 (tid,fp) 幂等——after_model 每轮重算别重复记）
                    try:
                        import json as _aj
                        import time as _t
                        from pathlib import Path as _P
                        _fpv = _hl.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12]
                        _key = (tid, _fpv)
                        if _key not in self._shown_seen:
                            self._shown_seen.add(_key)
                            if len(self._shown_seen) > 2000:
                                self._shown_seen.clear()
                            _f = _P(__file__).resolve().parent.parent / "mia_home" / "notes" / "approvals_log.jsonl"
                            _f.parent.mkdir(parents=True, exist_ok=True)
                            with open(_f, "a", encoding="utf-8") as _fh:
                                _fh.write(_aj.dumps({"ts": round(_t.time(), 1), "ev": "card_shown",
                                                     "tid": (tid or "?")[:8], "tool": nm, "fp": _fpv},
                                                    ensure_ascii=False) + "\n")
                    except Exception as _e2:
                        print(f"[gate] 批准账写失败（不挡路）：{_e2}", flush=True)
            if ask_pending:
                self._notify_feishu(ask_pending)
        return super().after_model(state, runtime)

    # ---- r41 待批飞书通知（Veda 第 4 炮的落地：人不在网页前不晾卡）----
    _notify_last: dict = {}   # {tid: ts} 60s 去重，批量卡只推一条

    def _notify_feishu(self, pending) -> None:
        import threading
        import time as _t
        tid = self._tid()
        now = _t.time()
        if not tid or now - (ConfirmGateC1._notify_last.get(tid) or 0) < 60:
            return
        ConfirmGateC1._notify_last[tid] = now
        names = "、".join(n for n, _ in pending[:4]) + ("…" if len(pending) > 4 else "")
        msg = (f"⏳ 米娅有 {len(pending)} 步等您扣章：{names}"
               f"（线程 {tid[:8]}）——打开办公室页面处理。")

        def _push():
            try:  # fire-and-forget：飞书挂了绝不影响弹卡主链
                from office.routers.lark import send_text
                r = send_text(msg)
                print(f"[feishu-notify] sent={r.get('ok')} err={r.get('error', '')[:80]}", flush=True)
            except Exception as e:
                print(f"[feishu-notify] FAIL {type(e).__name__}: {str(e)[:120]}", flush=True)
        threading.Thread(target=_push, daemon=True).start()


class SubGate(AgentMiddleware):
    """子层全拦件（R66 传导的机制化，Eve 问3/Lyra 问题3 采纳）：
    牛马/部门图不挂 ConfirmGateC1（子图 interrupt 无人批=挂死）——ask 类同样转
    文案沿链上报（"此操作需批准，写进产出上报"），deny 类同主层拒。
    主图收到上报后由总管在主线程触发工具（过主图 C1 批量卡）——爸爸永远只在
    主图上下文看到批准卡。
    继承官方 AgentMiddleware（裸类缺协议属性，10:2x 崩溃实证）。"""

    name = "sub_gate"

    def __init__(self, dept: str = "dept"):
        super().__init__()
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        self._proxy = ConfirmGateMiddleware(sub_mode=True)
        self.dept = dept  # 部门/岗位标识，进上报文案（Lyra）

    def _report(self, name: str, args, dec: str, pinned: bool = False) -> str:
        """上报文案（Lyra 格式）：工具名+参数预览+档位原因——总管代触发过主图卡时
        爸爸看到的上下文才完整（光有"请求批准 write_file"会批错）。
        hy4 十四轮 §③：pinned=True（本线程被压力钉降档）时在文案末尾追加一行固定话术
        ——读者（爸爸/总管/对账脚本）必须能分清"strict 来自设置真源"还是"来自临时降档"，
        后者不是政令变更、不该被当成档位改动的证据。同步/异步两钩共用本函数出文案。"""
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        line = (f"[子层请示][{self.dept}] {name} {ConfirmGateMiddleware._args_preview(name, args)}"
                f"\n原因={dec}档变更")
        if pinned:
            line += "\n（本线程临时降为变更前确认=压力降档，非设置真源变更）"
        return line

    def wrap_tool_call(self, request, handler):
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", "?"))
        args = tc.get("args")
        # D2 挂账四件③（hy4 十二轮 §1，09-15 爸爸令动工）：子层不再是盲区——
        # 档位统一经 ConfirmGateC1 单一判定处（含压力钉+TTL），被钉线程在子层同样
        # 受钉（原直读真源=主线程连败降档对牛马/部门图无效，而长任务主力失败正在子层）。
        # 子层失败计数仍不并账（那是 v0.3 并账设计项，本单不扩权）。
        # v0.3 件一（plan-d2-v03 §件一）：档与源经 level_and_source 一处判——废除
        # "lvl==strict 且 _pin_alive"二次推断（"真源改 strict+活钉"残余帧就此闭合：
        # 真源高档直接返回 (level,"true")，钉不参与；_pin_alive 惰性账副作用仍只一次）。
        lvl, src = ConfirmGateC1.level_and_source()
        pinned = (src == "pin")
        dec = self._proxy._decision(name, lvl, args)
        if dec == "pass":
            return handler(request)
        return ToolMessage(
            content=self._report(name, args, dec, pinned) + "\n" +
                    self._proxy._block_msg(name, lvl, dec, args),
            tool_call_id=tc.get("id", ""),
        )

    async def awrap_tool_call(self, request, handler):
        """异步版（同 C1：langgraph server 全异步，只写同步版必炸）。
        D2 四件③：与同步版同构走单一判定处（钉+TTL 覆盖子层），计数口径不分叉。"""
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", "?"))
        args = tc.get("args")
        # v0.3 件一：与同步版逐字同构（家规：计数与措辞口径绝不分叉）——
        # 档与源同样经 level_and_source 一处判，pinned 只认 source，
        # 不再有"lvl==strict 且 _pin_alive"的第二套推断。
        lvl, src = ConfirmGateC1.level_and_source()
        pinned = (src == "pin")
        dec = self._proxy._decision(name, lvl, args)
        if dec == "pass":
            return await handler(request)
        return ToolMessage(
            content=self._report(name, args, dec, pinned) + "\n" +
                    self._proxy._block_msg(name, lvl, dec, args),
            tool_call_id=tc.get("id", ""),
        )


def assert_gate_order(middlewares) -> None:
    """接线断言（Lyra P0 修法②配套）：**仅验 ConfirmGateC1 存在于主图 middleware 列表**
    （fail-closed：漏装=启动炸，不许静默）。不验顺序（语义即存在性保险丝）。
    子层三处（部门/主管/总管图）断言已由 cow_graphs.assert_dept_gates 实现（09-16 fix4），
    与本件同惯用法各管各面。"""
    names = [type(m).__name__ for m in middlewares]
    if "ConfirmGateC1" not in names:
        raise ValueError("C1 接线断言失败：主图 middleware 缺 ConfirmGateC1（fail-closed）")
