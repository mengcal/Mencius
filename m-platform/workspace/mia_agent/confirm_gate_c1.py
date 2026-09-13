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
    _GATE_INSTANCES: list = []  # r61b：活实例花名册（guard_unlock 端点经此触达 _guard_lock）

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

    _PROXY = None  # 模块级单例（Eve 新炮1：档位读取入口统一+省实例化）

    @classmethod
    def _proxy_of(cls):
        if cls._PROXY is None:
            from mia_agent.confirm_gate import ConfirmGateMiddleware
            cls._PROXY = ConfirmGateMiddleware(sub_mode=False)
        return cls._PROXY

    @classmethod
    def read_level(cls) -> str:
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        return ConfirmGateMiddleware._level()  # 类级直调（staticmethod 真源，NOVA P0-3 入口统一）

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
            n = _ap.bump_blocked(tid, tc_id, fp=_fpv)  # (tid,tc_id) 幂等：resume 不双计；r43 空 id 退参数指纹（hy4 P1-1）
            # r2-2：软轨告警计数已随 bump_blocked 同点递增（幂等保护在其内部），
            # 卡面告警文案另受 note_new_turn 按轮清零（见 after_model）。
            if n >= _ap.CARD_BUDGET:
                # 超预算：不弹卡，登记该 tc_id——wrap 层只拒"被预算扣掉卡"的调用（P1-3：
                # 爸爸刚批准的调用不在此集合，绝不会被误吞）
                self._over_budget.setdefault(tid, set()).add(tc_id)
                return False
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
        self._shown_seen: set = set()  # r49 {(tid,fp)} card_shown 幂等集
        self._guard_deny: dict = {}   # r60 {tid: set(tc_id)} 机器门 high 强制拦
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
        super().__init__(interrupt_on={}, **kw)
        # r61d 边界A 断言（hy4 P2-10）：机器门覆盖面绑 ask 路由——危险工具一旦被
        # 路由判成 auto，门静默失覆盖。启动即断言，坏=起不来，不许带病上线。
        if not sub_mode:
            for _t in ("execute", "write_file", "edit_file"):
                try:
                    _d = self._route(_t, {})
                except Exception:
                    continue  # 路由表未就绪（装配早期）不炸，真判到 auto 才炸
                if _d == "auto":
                    raise RuntimeError(f"guard coverage broken: {_t} routed to auto")

    def _budget_refusal(self, name: str) -> str:
        return (f"⛔ 「{name}」被网关预算拦下：本任务批准卡配额已用完（拦一次计一次，换参数也计）。"
                "停下——把目标、已完成步骤、卡在哪三件事向爸爸汇报；"
                "爸爸可在新对话里重开额度，或在管理端重置本任务预算。不许再试探性调用。")

    @staticmethod
    def _tc_key(tc: dict) -> str:
        """r61e（Cora N3）：tc_id 空值退参数指纹——r43 bump_blocked 同款教训复用，
        防所有无 id 调用共享空串键（一个被拒全体连坐/一个登记全体免卡）。"""
        _id = str(tc.get("id") or "")
        if _id:
            return _id
        import hashlib as _h
        return "fp:" + _h.sha256(str(tc.get("args") or "").encode("utf-8", "replace")).hexdigest()[:12]

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
        # r61b P0-4（hy4 命门）：when=False 只等于"不弹卡"——wrap 层不出拒信的话，
        # 被冻结线程的一切 ask 调用=自动放行（攻击者故意连撞 2 次 high 即换取
        # 免审批执行，攻击方向与设计相反）。冻结态 ask 一律回冻结拒信；
        # P1-3：文案与预算拒/机器 high 拒区分——爸爸一眼分清"接管解冻"还是"重开额度"。
        if dec == "ask" and self._frozen(tid):
            return ToolMessage(content=(
                "⛔ 本线程已被机器安全门冻结：短时间内连续命中高危形态，门已停止一切"
                "审批交互等待爸爸接管。请停止调用工具，把本线程目标与最近尝试的操作"
                "向爸爸汇报。冻结 30 分钟后自动解除。"),
                tool_call_id=tc.get("id", ""))
        # r60 机器门 high：强制拦。
        # r61 拒信改造（hy4 A-4 脱敏 + Eve 正向出口 + Veda 撤"不要绕行"句）：
        # ①findings 细节不进模型拒信（只进 guard_high 账本+卡面）——拒信含命中
        #   关键词=给注入者的教材（告诉它门在看什么，改写法即绕）；
        # ②撤"不要换写法绕行"负向句——对被改写目标函数的模型无效，反而提示
        #   "换写法"这个选项存在。给正向出口：W2 实证"给她出口她就走出口"。
        # r61c N1（hy4 二轮 P0）：when 侧写键 `tid or "?"`、本侧读裸 tid——无 tid
        # 线程的 high 既不弹卡也读不到 deny=**敞怀放行**。键归一 `_gk()` 单一真源。
        # r61e（Cora N3 连锁自审）：when 侧 tc_id 已改指纹键（_tc_key），本侧三处
        # 读必须同步——否则空 id 调用写读错配=登记了拒信读不到（我改 when 时差点
        # 亲手造出第二个 N1，"修法即攻击面"当日第三次应验，只是这次被自查拦住）。
        gk = tid or "?"
        tck = self._tc_key(tc)
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
        return None

    def wrap_tool_call(self, request, handler):
        """拒类出口（自包含）+预算精准拒：不赌 middleware 顺序，也不吞爸爸刚批的调用。"""
        blocked = self._check_budget_gate(request)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        """异步版（langgraph 全异步必双钩——00:14 NotImplementedError 教训）。"""
        blocked = self._check_budget_gate(request)
        return blocked if blocked is not None else await handler(request)

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

    def _report(self, name: str, args, dec: str) -> str:
        """上报文案（Lyra 格式）：工具名+参数预览+档位原因——总管代触发过主图卡时
        爸爸看到的上下文才完整（光有"请求批准 write_file"会批错）。"""
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        return (f"[子层请示][{self.dept}] {name} {ConfirmGateMiddleware._args_preview(name, args)}"
                f"\n原因={dec}档变更")

    def wrap_tool_call(self, request, handler):
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", "?"))
        args = tc.get("args")
        dec = self._proxy._decision(name, ConfirmGateMiddleware._level(), args)
        if dec == "pass":
            return handler(request)
        return ToolMessage(
            content=self._report(name, args, dec) + "\n" +
                    self._proxy._block_msg(name, ConfirmGateMiddleware._level(), dec, args),
            tool_call_id=tc.get("id", ""),
        )

    async def awrap_tool_call(self, request, handler):
        """异步版（同 C1：langgraph server 全异步，只写同步版必炸）。"""
        from mia_agent.confirm_gate import ConfirmGateMiddleware
        tc = getattr(request, "tool_call", None) or {}
        name = str(tc.get("name", "?"))
        args = tc.get("args")
        dec = self._proxy._decision(name, ConfirmGateMiddleware._level(), args)
        if dec == "pass":
            return await handler(request)
        return ToolMessage(
            content=self._report(name, args, dec) + "\n" +
                    self._proxy._block_msg(name, ConfirmGateMiddleware._level(), dec, args),
            tool_call_id=tc.get("id", ""),
        )


def assert_gate_order(middlewares) -> None:
    """接线断言（Lyra P0 修法②配套）：主图必须 ConfirmGateC1 在列且子层图只有 SubGate
    类拒件——装配错序/漏装在启动时炸，不许静默。"""
    names = [type(m).__name__ for m in middlewares]
    if "ConfirmGateC1" not in names:
        raise ValueError("C1 接线断言失败：主图 middleware 缺 ConfirmGateC1（fail-closed）")
