# -*- coding: utf-8 -*-
"""PlanCheckMiddleware —— 流程体系 v2 层2（09-13 夜窗落码）。

三件（全部来自基线实测/五家+hy4 评审收敛）：
  A. 验收注入：每轮模型调用前把 task_brief 机械提取的验收清单写进 system——
     「系统提取自爸爸原话，非你的转述」（W5 铁证：模型自评不可信，核对是代码动词，
     但注入面让米娅每轮都看得见要核对什么——双通道：代码核对是硬闸，注入是导航）。
  B. clarify 路由：task_brief 判定 needs_clarification → 注入"先问爸爸验收标准，
     问是免费的，别猜一个标准再自己满足它"（NOVA：模糊任务 fallback: ask）。
  C. 同型×3 硬拦：与观测器联动——同 tid 连续 3 次同类作用域 flag（如 out-of-scope:/notes
     三连撞，C5 实证告警文案不叫停）→ PlanCheck 在 after_model 返回一条 system
     提醒消息（软拦一期：提醒+上报，不砍 run；硬拦开关进设置）。

继承 AgentMiddleware（双钩教训：同步+异步齐写）。
"""
from __future__ import annotations

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage


class PlanCheckMiddleware(AgentMiddleware):
    name = "plan_check"

    def __init__(self, hard_block: bool = False):
        super().__init__()
        self._hard = hard_block

    # ---- A/B：每轮注入验收导航 ----
    def _inject(self, request) -> None:
        try:
            from langgraph.config import get_config
            tid = str((get_config().get("configurable") or {}).get("thread_id", "") or "")
            if not tid:
                return
            from mia_agent import task_brief as _tb
            b = _tb.get_brief(tid)
            if not b:
                return
            lines = []
            items = _tb.acceptance_for(tid)
            if items:
                got = "；".join(f"{i['value']}({i['role']})" for i in items[:6])
                lines.append(f"【验收导航·系统提取自爸爸原话，不是你的转述】目标字面量：{got}。"
                             "完成后逐项核对，汇报用两栏：任务要的是 X｜产物是 Y。"
                             "forbidden 项绝对不许出现在产物里；old-value 项必须已消失。")
            if b.get("clarify"):
                lines.append("【验收标准未定】本任务没从原话提到可核对的目标——"
                             "先问爸爸要什么（问是免费的），别猜一个标准再自己满足它。")
            if lines:
                sp = getattr(request, "system_prompt", "") or ""
                request.system_prompt = sp + "\n\n" + "\n".join(lines)
        except Exception as e:
            # 失败要出声（静默 pass 曾把注入失效藏了两轮调试）——节流：打印不挡路
            print(f"[plan-check] 注入失败（不挡路）：{type(e).__name__}: {e}", flush=True)

    def wrap_model_call(self, request, handler):
        self._inject(request)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        self._inject(request)
        return await handler(request)

    # ---- C：同型×3 连撞提醒（软拦一期）----
    def after_model(self, state, runtime):
        return self._check_streak(state)

    async def aafter_model(self, state, runtime):
        return self._check_streak(state)

    def _check_streak(self, state):
        try:
            from mia_agent.flow_observer import observer
            tid = observer._tid()
            seq = [r for r in observer._runs.get(tid, []) if r.get("flags")]
            if len(seq) < 3:
                return None
            last3 = seq[-3:]
            # 同型=同 flag 前缀（out-of-scope:/notes 与 out-of-scope:/notes/x 同型）
            def kind(f):
                return f.split(":")[0] + ":" + (f.split(":", 1)[1].split("/")[1] if ":" in f and "/" in f.split(":", 1)[1] else "")
            kinds = {tuple(sorted(kind(f) for f in r["flags"])) for r in last3}
            if len(kinds) == 1 and not self._hard:
                return {"messages": [SystemMessage(content=(
                    "⚠️ PlanCheck：同一类作用域错误已连撞 3 次（观测器同型判定）。"
                    "停下来——把目标、已试过的路径、卡点向爸爸汇报（问是免费的），"
                    "别再换参数试第 4 次。常见根因：execute 里写了 /notes/ 绝对形式"
                    "（应写相对路径 notes/）。") )]}
            return None
        except Exception:
            return None
