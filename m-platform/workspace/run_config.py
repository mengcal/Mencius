# -*- coding: utf-8 -*-
"""run_config.py — 每轮运行级配置（2026-08-29 作者）

对话输入框的两个开关真正生效的地方：
- 输入框选的模型 → 前端随消息带 mia_config.model → 本中间件在模型调用前换主脑
- 输入框联网开关 → mia_config.web_search=false → 搜索工具被挡回"已关闭"

原则：官方机制（AgentMiddleware + 自定义 state 通道 mia_config），不碰消息文本，
不改助手提示词，什么都不选 = 完全默认行为。
"""
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

SEARCH_TOOLS = {
    "web_search", "web_search_metaso", "web_search_bocha",
    "web_search_tavily", "web_search_searxng", "web_search_bing",
}


def _cfg(request) -> dict:
    try:
        return (request.state or {}).get("mia_config") or {}
    except Exception:
        return {}


def _model_for(request, model_name: str, thinking=None, provider: str | None = None):
    """构造运行时模型。provider 给定时精确锁定该服务商（2026-08-29 管理员的三个智谱
    烧错额度的教训：同名模型谁排前用谁不行，必须认准管理员选的那家）。"""
    if not model_name:
        return None
    try:
        from settings_mgr import load_settings
        plist = load_settings().get("external", {}).get("providers", [])
        candidates = [p for p in plist if p.get("enabled", True) and
                      (not provider or p.get("name") == provider)]
        for p in candidates:
            if model_name in (p.get("models_cache") or []) or provider:
                from providers import make_model
                kwargs = {}
                if thinking not in (None, "", "default"):
                    kwargs["thinking"] = thinking
                return make_model(p["name"], model_name, **kwargs)
    except Exception:
        pass
    return None


def _tool_blocked(cfg: dict, name: str, request, result_of) -> bool:
    if not cfg.get("web_search", True) and name in SEARCH_TOOLS:
        return True
    return False


def _record_usage(model_name: str, result):
    """把每次模型调用的 token 用量追加到 mia_home/usage.jsonl（按日按模型累计的原始流水）。
    额度提醒/自动切换的数据源。任何异常都吞掉，绝不影响对话。
    R44 修正：wrap_model_call 的 handler 返回可能是 ModelResponse/消息列表/单消息，
    usage_metadata 在消息对象上——逐层挖出来，挖不到就跳过（旧行为是永远挖不到=空转）。"""
    try:
        usage = getattr(result, "usage_metadata", None) or {}
        if not usage:
            msgs = getattr(result, "result", None)
            if msgs is None and isinstance(result, list):
                msgs = result
            if msgs is not None:
                for m in (msgs if isinstance(msgs, list) else [msgs]):
                    um = getattr(m, "usage_metadata", None) or (m.get("usage_metadata") if isinstance(m, dict) else None)
                    if um:
                        usage = um
                        break
        if not usage:
            return
        import json as _json
        from datetime import date, datetime as _dt, timezone as _tz, timedelta as _td
        _CN = _dt.now(_tz(_td(hours=8)))  # 北京时区（容器是 UTC，date.today() 会早 8 小时跨天）
        from pathlib import Path
        # R53：线程 ID（上下文容量图按线程统计）
        tid = ""
        try:
            from langgraph.config import get_config
            tid = (get_config() or {}).get("configurable", {}).get("thread_id", "")
        except Exception:
            pass
        f = Path(__file__).resolve().parent / "mia_home" / "usage.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fp:
            fp.write(_json.dumps({
                "date": _CN.date().isoformat(),
                "ts": _CN.strftime("%Y-%m-%d %H:%M:%S"),
                "thread": tid,
                "model": model_name,
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _now_bj() -> str:
    """R64 时间感知：每轮模型调用前注入当前北京时间。
    时间与记忆不可分割（管理员 2026-08-31 定调）——没有时间锚，记忆就没有顺序。"""
    from datetime import datetime, timezone, timedelta

    bj = timezone(timedelta(hours=8))
    now = datetime.now(bj)
    week = "一二三四五六日"[now.weekday()]
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} 周{week}（北京时间）"


def _inject_time(request):
    """R64 时间感知（R64 修正）：把当前北京时间追加进本轮 system prompt。
    每轮模型调用前实时取 datetime.now()（服务端时钟），与 open-webui 的 {{CURRENT_DATE}}
    模板变量、酒馆的 {{date}} {{time}} 宏同理——运行时替换，不是写死的字符串。
    只注入「感知」，不要求模型在回复里写时间戳——那是前端渲染的活，不烧令牌。"""
    try:
        sp = getattr(request, "system_prompt", "") or ""
        request.system_prompt = (
            sp + f"\n\n【当前时间】{_now_bj()}。"
            f"涉及日期/时段/「今天」「刚才」等话题，一律以此刻为准。"
        )
    except Exception:
        pass


# R73（2026-09-03 管理员拍板）：角色卡 profile 系统整体退役——三轮外部评审一致认定
# "卡只换人设不摘工具=权限裸奔"，与工作平台冲突风险大于价值（聊天有助手，角色扮演有酒馆，工程有 ZCode）。
# 原 _character_of/_CHAR_REGISTRY/挂卡换脑逻辑已全部移除；历史设计与教训见 eng-log R70/R73 与 [[m-platform-incidents]]。


class RunConfigMiddleware(AgentMiddleware):
    # ---- 模型调用前：按 mia_config 换主脑模型 + 思维档位 + 注入当前时间（R64） ----
    @staticmethod
    def _thinking_for(cfg: dict) -> str:
        """R79⑥（管理员定的 A+B 方案·评审C 成本洞）：思维档回退链 mia_config.thinking（聊天框，交互回合）
        → boss 岗默认（settings.agents.boss.thinking，webhook/定时等非交互回合）→ off。
        旧逻辑非交互回合拿不到 thinking 直接落"模型默认思考"=自动任务悄悄烧钱，现统一收口到 off 兜底。"""
        t = cfg.get("thinking")
        if t not in (None, "", "default"):
            return t
        try:
            from settings_mgr import load_settings
            t = ((load_settings().get("agents") or {}).get("boss") or {}).get("thinking")
        except Exception:
            t = None
        return t if t in ("off", "low", "medium", "high") else "off"

    def wrap_model_call(self, request, handler):
        cfg = _cfg(request)
        want = str(cfg.get("model") or "").strip()
        used = want
        if want:
            m = _model_for(request, want, self._thinking_for(cfg), cfg.get("provider"))
            if m is not None:
                request.model = m
        _inject_time(request)
        try:
            result = handler(request)
        except Exception:
            # R49 回退链：主模型异常（429/余额不足/网络）→ 按配置依次换备用模型重试
            result = self._run_fallbacks(request, handler)
            if result is None:
                raise
        _record_usage(used or getattr(request.model, "model_name", "unknown"), result)
        return result

    async def awrap_model_call(self, request, handler):
        cfg = _cfg(request)
        want = str(cfg.get("model") or "").strip()
        used = want
        if want:
            m = _model_for(request, want, self._thinking_for(cfg), cfg.get("provider"))
            if m is not None:
                request.model = m
        _inject_time(request)
        try:
            result = await handler(request)
        except Exception:
            result = await self._arun_fallbacks(request, handler)
            if result is None:
                raise
        _record_usage(used or getattr(request.model, "model_name", "unknown"), result)
        return result

    # ---- R49 回退链：设置页 settings.agents.boss.fallbacks 顺序重试（同款 make_model 构造）----
    def _run_fallbacks(self, request, handler):
        for fb in self._fallback_models():
            try:
                print(f"[fallback] 主模型异常，降级到 {fb.get('provider')}/{fb.get('model')}", flush=True)
                request.model = fb
                return handler(request)
            except Exception:
                continue
        return None

    async def _arun_fallbacks(self, request, handler):
        for fb in self._fallback_models():
            try:
                print(f"[fallback] 主模型异常，降级到 {fb.get('provider')}/{fb.get('model')}", flush=True)
                request.model = fb
                return await handler(request)
            except Exception:
                continue
        return None

    @staticmethod
    def _fallback_models():
        """回退链唯一真源 = 设置页 settings.agents.boss.fallbacks（管理员自己填自己选）。
        无缓存（改了即时生效）、无 agents_config.json 兜底（配置页删了就没了，符合"零硬编码"原则）。"""
        models = []
        try:
            from settings_mgr import load_settings
            from providers import make_model  # R68 修 评审B🔴1/评审E三.2.1：旧版没这行→NameError 被下条 except 吞→回退链从未生效
            fbs = ((load_settings().get("agents") or {}).get("boss") or {}).get("fallbacks") or []
            for fb in fbs:
                try:
                    kwargs = {k: v for k, v in fb.items() if k in ("temperature", "max_tokens", "thinking")}
                    models.append(make_model(fb.get("provider", ""), fb.get("model", ""), **kwargs))
                except Exception as e:
                    print(f"[fallback] ⚠ 备用档 {fb.get('provider')}/{fb.get('model')} 构造失败（跳过该档）：{e}", flush=True)
        except Exception as e:
            print(f"[fallback] ⚠ 回退链读取失败：{e}", flush=True)
        return models

    # ---- 工具调用：联网关了就挡回搜索工具 ----
    def wrap_tool_call(self, request, handler):
        cfg = _cfg(request)
        name = (request.tool_call or {}).get("name", "")
        if cfg.get("web_search", True) is False and name in SEARCH_TOOLS:
            return ToolMessage(
                content="（联网搜索当前已在输入框关闭。如需搜索请打开 🌐 开关后重试。）",
                tool_call_id=(request.tool_call or {}).get("id", ""),
            )
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        cfg = _cfg(request)
        name = (request.tool_call or {}).get("name", "")
        if cfg.get("web_search", True) is False and name in SEARCH_TOOLS:
            return ToolMessage(
                content="（联网搜索当前已在输入框关闭。如需搜索请打开 🌐 开关后重试。）",
                tool_call_id=(request.tool_call or {}).get("id", ""),
            )
        return await handler(request)
