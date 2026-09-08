# -*- coding: utf-8 -*-
"""providers.py — mcal 函数式模型工厂

管理员要的：用函数设主模型 + 多模型子代理。
每个服务商（base_url + api_key + 默认模型）在 providers.json 里配，
make_model(provider, model) 一个函数出模型实例，主脑/子代理随便换。

服务商一览（2026-08-24）：
  ss   书生浦语 intern-latest（9000万/月免费）
  temp 智谱 glm-4.5-air
  ds   DeepSeek deepseek-v4-flash
  mt   长猫 LongCat-2.0
  bl   阿里百炼 qwen3.7-flash
  zp   智谱 glm-5.2
"""
import json
import os
from functools import lru_cache
from pathlib import Path

from langchain_openai import ChatOpenAI

PROVIDERS_FILE = Path(__file__).resolve().parent / "providers.json"


def _model_override(model_name: str) -> dict:
    """管理员按模型单独设置（settings.json 的 model_overrides 节，2026-08-29 作者）。

    参数三层优先级 = 代码显式传入 > model_overrides.<模型名> > 全局默认。
    取不到/没配置返回空 dict，零影响。
    """
    try:
        from settings_mgr import load_settings
        return (load_settings().get("model_overrides", {}) or {}).get(model_name, {}) or {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_providers_file() -> dict:
    """读 providers.json（遗留兼容层）。新服务商一律走设置页"外部连接"（存 settings.json）。
    R69（评审E三.2.6）：文件缺失=空表——遗留兼容层不得成为启动硬依赖。"""
    try:
        return json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_providers() -> dict:
    """统一服务商表 = providers.json（遗留）+ 设置页外部连接（来源真相，enabled 才算）。
    设置页添加的服务商（external.providers）优先级更高；同名时覆盖遗留条目。
    返回 {key: {base_url, api_key, model}}——工人岗矩阵和 /providers 接口都吃这张表，
    从此加服务商不用碰任何文件，设置页点几下就行（2026-08-29 作者）。"""
    merged = dict(_load_providers_file())
    try:
        from settings_mgr import load_settings, get_plain_provider_key
        for p in load_settings().get("external", {}).get("providers", []):
            if not p.get("enabled", True):
                continue
            name = p.get("name", "")
            if not name or not p.get("base_url"):
                continue
            key = get_plain_provider_key(name) or ""
            # 密钥隔离原则：设置页条目必须有明文 key 才能覆盖/新增；
            # key 为空且遗留表里有同名条目 → 保留遗留（绝不让空 key 顶掉能用密钥，
            # 2026-08-29 踩坑：空覆盖导致 ChatOpenAI Missing credentials 容器起不来）
            if not key:
                if name in merged:
                    continue
                merged[name] = {
                    "base_url": p["base_url"].rstrip("/"),
                    "api_key": "",
                    "model": (p.get("models_cache") or [""])[0] if p.get("models_cache") else "",
                }
                continue
            merged[name] = {
                "base_url": p["base_url"].rstrip("/"),
                "api_key": key,
                "model": (p.get("models_cache") or [""])[0] if p.get("models_cache") else "",
            }
    except Exception:
        pass
    return merged


def make_model(provider_name: str, model_name: str = "", **kwargs) -> ChatOpenAI:
    """函数式模型工厂：按服务商名 + 模型名构造 ChatOpenAI（OpenAI 兼容协议）。

    参数：
        provider_name: providers.json 里的 key（ss/temp/ds/mt/bl/zp）
        model_name:    模型名，留空用服务商默认
        thinking:      None=默认不动；False=关闭思考；True=开启思考。
                       书生(ss)默认 False(关思考)：省 token、响应快，应对 RPM30/TPM300K 限流。
                       （实测关闭思考 9.7s vs 开启 14.6s，省34%时间）
        **kwargs:      透传 ChatOpenAI 参数（temperature/max_tokens 等）

    用法：
        main = make_model("temp", "glm-4.5-air")          # 主模型
        coder = make_model("ds", "deepseek-v4-flash")     # 代码子代理
        visual = make_model("ss", "intern-latest", thinking=True)  # 识图要思考
    """
    providers = load_providers()
    if provider_name not in providers:
        raise KeyError(f"未知服务商: {provider_name}，可选: {list(providers)}")
    p = providers[provider_name]
    model = model_name or p.get("model", "")
    # 魔搭偶发 429 限流/响应慢 → 给模型加自动重试 + 请求超时
    max_retries = kwargs.pop("max_retries", 3)
    request_timeout = kwargs.pop("request_timeout", 90)

    # ===== 思考控制（管理员四档：关闭/低/中/高；字符串档位或 True/False）=====
    # 各家协议不同，按 base_url 域名适配；档位只分"关/开"两级的厂商，低中高都按开处理。
    thinking = kwargs.pop("thinking", None)  # None=不动（但书生默认关思考，见下）
    if thinking is None and provider_name == "ss":
        thinking = False  # 历史行为：书生默认关思考（省 token 快）
    extra_body = dict(kwargs.pop("extra_body", {}) or {})
    if thinking is not None:
        host = (p.get("base_url") or "").split("//")[-1].split("/")[0]
        off = thinking in (False, "off", "关闭")
        if "bigmodel" in host:  # 智谱 GLM
            extra_body["thinking"] = {"type": "disabled" if off else "enabled"}
        elif "deepseek" in host:  # DeepSeek（官方：thinking 开关 + reasoning_effort low/medium/high；medium 实际映射 high）
            if off:
                extra_body["thinking"] = {"type": "disabled"}
            elif thinking in ("low", "medium", "high"):
                extra_body["reasoning_effort"] = thinking
        elif "intern-ai" in host:  # 书生
            extra_body["thinking_mode"] = not off
        elif "dashscope" in host or "aliyuncs" in host:  # 评审E
            extra_body["enable_thinking"] = not off
        elif off:
            extra_body["reasoning"] = {"enabled": False}

    # ===== 管理员按模型覆盖（设置页 model_overrides）=====
    # 只在调用方没有显式传参时生效，代码里显式指定的值优先级最高
    ov = _model_override(model)
    if "temperature" not in kwargs and str(ov.get("temperature", "")) != "":
        kwargs["temperature"] = float(ov["temperature"])
    if "max_tokens" not in kwargs and str(ov.get("max_tokens", "")) != "":
        kwargs["max_tokens"] = int(ov["max_tokens"])
    if "top_p" not in kwargs and str(ov.get("top_p", "")) != "":
        kwargs["top_p"] = float(ov["top_p"])

    return ChatOpenAI(
        model=model,
        # 无 key 就占位、调用时才报错；绝不借 .env 别家 key 越权（管理员零硬编码原则：配置页是唯一源）
        api_key=p["api_key"] or "EMPTY",
        base_url=p["base_url"],
        temperature=kwargs.pop("temperature", 0.7),
        max_tokens=kwargs.pop("max_tokens", 2048),
        max_retries=max_retries,
        request_timeout=request_timeout,
        extra_body=extra_body or None,
        **kwargs,
    )


def list_providers() -> list[str]:
    """列出所有可用服务商名"""
    return list(load_providers().keys())
