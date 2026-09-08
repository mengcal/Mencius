# -*- coding: utf-8 -*-
"""mia_agent/models.py —— 工人岗矩阵配置 + 模型构造
拆分来源：D:\\m\\workspace\\agent_multimodel.py 原 L124（make_model import）、
L858-908（拆分方案 #5；其中 L893-900 的 boss_model 构造在本段行号范围内，一并归入）。
依赖：providers.make_model、settings_mgr.load_agents_config（模块级）；
langchain_openai 在 _model 兜底分支内懒加载（与原实现一致）。
被引用：mia_agent/graph.py（boss_model，原 L939/L1012；_interrupt_on，原 L1016）。
"""

from providers import make_model  # 原 L124

# ============ 工人岗矩阵唯一真源 = 设置页 settings.agents（R65 去重：直用 settings_mgr，不再二份 loader） ============（原 L858）
from settings_mgr import load_agents_config  # 原 L859

_CFG = load_agents_config()  # 原 L861


def _model(key: str, **kwargs):  # 原 L864-880
    """按 key 从设置页 settings.agents 读 provider+model 构造模型实例。
    配置错/服务商不可用 → 只留占位模型让平台起得来（启动成功、调用才报错）。
    R65 管理员铁律：越权兜底已删——绝不偷换别的服务商干活，没配好就报空不干活。"""
    c = _CFG.get(key) or {}
    try:
        # 工人岗可自带 thinking 档位（settings.agents 里 "thinking": "off/low/medium/high"，助手可改）
        t = c.get("thinking")
        kw = dict(kwargs)
        if t not in (None, "", "default") and "thinking" not in kw:
            kw["thinking"] = t
        return make_model(c.get("provider", ""), c.get("model", ""), **kw)
    except Exception as e:
        print(f"[agent] 警告：{key} 的配置「{c.get('provider')}/{c.get('model')}」不可用：{e}——"
              f"用占位模型顶替（绝不自作主张换服务商），请到设置页修正后重启。", flush=True)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="unconfigured", api_key="EMPTY", base_url="https://unconfigured.invalid")


def _global_params() -> dict:  # 原 L883-890
    """用户全局模型参数（设置页 通用→Model parameters，存 general.params）。
    三层优先级 = 代码显式 > model_overrides(按模型) > general.params(全局)。"""
    try:
        from settings_mgr import load_settings
        return load_settings().get("general", {}).get("params", {}) or {}
    except Exception:
        return {}


# 工作者组长（拆派汇总）（原 L893-900）
_gp = _global_params()
_boss_kwargs = {}
if str(_gp.get("temperature", "")) != "":
    _boss_kwargs["temperature"] = float(_gp["temperature"])
if str(_gp.get("max_tokens", "")) != "":
    _boss_kwargs["max_tokens"] = int(_gp["max_tokens"])
boss_model = _model("boss", **_boss_kwargs)
# R49 回退链改由 run_config.py 的模型调用层实现（异常时换备用模型重试），配置见设置页 settings.agents.boss.fallbacks（原 L901）


def _interrupt_on():  # 原 L904-908
    """R47：官方 HumanInTheLoop 已停用（interrupt_on 启动时烘焙，不能动态调档）。
    确认全部改走 ConfirmGateMiddleware 动态确认门——四档、改设置即时生效、无需重启。
    本函数保留返回空（万一设置页旧值残留也不双重要求确认）。"""
    return []
