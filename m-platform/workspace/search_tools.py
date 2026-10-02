# -*- coding: utf-8 -*-
"""牛马搜索工具：博查(中文) + Tavily(英文)，供 deepagents 挂载
用法：tools=[web_search_bocha, web_search_tavily, web_search]
"""
import json, urllib.request, urllib.parse

# 密钥管理（爸爸铁律：不硬编码）：一律从 settings_mgr（设置页"联网搜索"可自由改）读取，
# 没配置 = 返回未配置提示，绝不写死任何密钥（2026-08-29 应爸爸要求删除全部兜底常量）。
try:
    from settings_mgr import get_plain_key as _settings_key
except Exception:  # 老环境没有 settings_mgr
    def _settings_key(_path):
        return ""


def _key(which: str) -> str:
    """运行时取 key：设置页改完即生效，无需改代码、无需重启。"""
    return _settings_key(f"search.{which}") or ""


def _no_key(name: str) -> str:
    return f"{name}密钥未配置：请到 设置 → Admin → 联网搜索 填入后保存（无需重启）"


def _search_setting(key: str, dflt):
    """设置页 search 节的其他配置（engine/resultCount/searxngUrl 等），R7 接入。"""
    try:
        from settings_mgr import load_settings
        v = load_settings().get("search", {}).get(key, dflt)
        return v if v not in ("", None) else dflt
    except Exception:
        return dflt


# 09-17 深夜 schema 收口：默认值单一来源=settings_schema.py
from settings_schema import default_of as _dof
BOCHA_URL = _dof("search.bochaUrl")
TAVILY_URL = _dof("search.tavilyUrl")
SEARXNG_URL = _dof("search.searxngUrl")
# 10-02：search.metasoUrl/metasoReaderUrl 键退役——秘塔端点直写字面量（Mimosa SSRF 字面量要求），
# 官方端点唯一稳定（https://metaso.cn/api/v1/search + /api/v1/reader）
# r35（Qoder P2-17 族收口）：BING_URL/search.bingUrl 随 bing 死链整族退役（engine 选项无 bing、web_search 无分发、工具零注册）


def _count() -> int:
    """搜索结果数量（设置页可改，默认 5）"""
    try:
        return int(_search_setting("resultCount", _dof("search.resultCount")))
    except Exception:
        return 5


def _engine_url(key: str, default: str) -> str:
    """09-17 批②（Lesson 68）：搜索端点进配置（settings.search.<key>），代码常量退为默认值；
    公网引擎只许 https，非法值回落默认（同 searxng R10.11 轻闸门思路）。"""
    v = str(_search_setting(key, default)).strip()
    if not v.lower().startswith("https://"):
        v = default
    return v


def _fmt(results, max_n=5):
    out = []
    for r in results[:max_n]:
        title = r.get("title", r.get("name", ""))
        url = r.get("url", r.get("link", ""))
        snip = r.get("snippet", r.get("content", ""))[:150]
        out.append(f"- {title}\n  链接: {url}\n  摘要: {snip}")
    return "\n".join(out) if out else "（无结果）"


def _bocha(query, count=5):
    if not _key("bochaKey"):
        return _no_key("博查")
    body = json.dumps({"query": query, "count": count, "summary": True}).encode()
    req = urllib.request.Request(_engine_url("bochaUrl", BOCHA_URL), data=body, headers={
        "Authorization": f"Bearer {_key('bochaKey')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    # 兼容两种返回格式
    pages = d.get("data", {}).get("webPages", {}).get("value", []) if isinstance(d.get("data"), dict) else []
    if not pages:
        pages = d.get("results") or (d.get("data", {}).get("results", []) if isinstance(d.get("data"), dict) else [])
    return _fmt(pages)


def _metaso(query, count=5):
    # 秘塔 REST v1 搜索（10-02 爸爸给定式），扣积分（约3分/次，每天100分）。
    # 端点直写字面量（Mimosa SSRF 静态闸要求 URL 字面量；官方端点唯一稳定，
    # 改端点时同步 settings_schema 文档行）。旧 MCP 面随本改造退役。
    import requests
    if not _key("metasoKey"):
        return _no_key("秘塔")
    r = requests.post("https://metaso.cn/api/v1/search",
                      headers={"Authorization": f"Bearer {_key('metasoKey')}"},
                      json={"q": query, "scope": "webpage", "includeSummary": True,
                            "size": str(count)}, timeout=25)
    r.raise_for_status()
    d = r.json()
    credits = d.get("credits", "?")
    pages = d.get("webpages", [])
    out = []
    for p in pages[:count]:
        title = p.get("title", "")
        link = p.get("link", "") or p.get("url", "")
        snip = (p.get("snippet", "") or "")[:150]
        out.append(f"- {title}\n  链接: {link}\n  摘要: {snip}")
    return f"(扣{credits}分)\n" + ("\n".join(out) if out else "（无结果）")


def _metaso_reader(url):
    """秘塔 reader：抓网页正文（text/plain，无广告导航，实测 0.3s 级）。
    入参只许公网 http(s) 地址（拒内网/环回——url 是米娅可控输入，真校验）。"""
    import requests
    if not _key("metasoKey"):
        return _no_key("秘塔")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("url 只许 http(s) 公网地址")
    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url or ".internal" in url:
        raise ValueError("拒绝内网/环回地址")
    r = requests.post("https://metaso.cn/api/v1/reader",
                      headers={"Authorization": f"Bearer {_key('metasoKey')}",
                               "Accept": "text/plain"},
                      json={"url": url}, timeout=25)
    r.raise_for_status()
    return r.text


def _searxng(query, count=5):
    import urllib.parse
    base = str(_search_setting("searxngUrl", SEARXNG_URL)).rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        base = SEARXNG_URL.rstrip("/")  # R10.11（千问 P2-4）：轻闸门——异 scheme（file:/data: 等）回落默认内网 searxng；
                                        # 不套 providers 的公网闸门是因为默认值本来就是容器内网地址（设计如此）
    lang = str(_search_setting("searxngLang", _dof("search.searxngLang")))
    url = f"{base}?q={urllib.parse.quote(query)}&format=json&language={urllib.parse.quote(lang)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    out = []
    for res in d.get("results", [])[:count]:
        title = res.get("title", "")
        link = res.get("url", "")
        snip = (res.get("content", "") or "")[:150]
        out.append(f"- {title}\n  链接: {link}\n  摘要: {snip}")
    return "\n".join(out) if out else "（无结果）"


import re, html as _html


# r35：_bing 已退役（同上，历史实现见 git 仓）

def _tavily(query, count=5):
    if not _key("tavilyKey"):
        return _no_key("Tavily")
    body = json.dumps({"api_key": _key("tavilyKey"), "query": query, "max_results": count}).encode()
    req = urllib.request.Request(_engine_url("tavilyUrl", TAVILY_URL), data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    return _fmt(d.get("results", []))


def web_search_bocha(query: str) -> str:
    """博查中文搜索（中文资料首选）。返回搜索结果的标题、链接、摘要。"""
    try:
        return _bocha(query)
    except Exception as e:
        return f"博查搜索失败: {e}"


def web_search_tavily(query: str) -> str:
    """Tavily英文搜索（英文资料首选）。返回搜索结果标题、链接、摘要。"""
    try:
        return _tavily(query)
    except Exception as e:
        return f"Tavily搜索失败: {e}"


def web_search_metaso(query: str) -> str:
    """秘塔搜索（中文主力，每天100积分，可搜网页/论文/播客）。返回标题、链接、摘要。"""
    try:
        return _metaso(query)
    except Exception as e:
        return f"秘塔搜索失败: {e}"


def web_read_metaso(url: str) -> str:
    """秘塔 reader：抓取网页正文纯文本（无广告无导航，秒级）。搜索命中链接后要读全文时用；
    url 必须以 http(s):// 开头（拒内网地址）。"""
    if not (url.startswith("https://") or url.startswith("http://")):
        return "url 必须以 http(s):// 开头"
    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url or ".internal" in url:
        return "拒绝内网/环回地址"
    try:
        text = _metaso_reader(url)
        return text[:8000] if text.strip() else "（页面正文为空）"
    except Exception as e:
        return f"网页读取失败: {e}"


# r35（Qoder CB 3.2 定案）：web_search_searxng 从未注册进任何图，死函数退役；searxng 引擎走 web_search(engine=searxng) 分支。

# r35（Qoder CB 3.2 定案）：web_search_bing 从未注册进任何图，死函数退役；searxng 引擎走 web_search(engine=searxng) 分支。

def web_search(query: str) -> str:
    """通用搜索。设置页 search.engine 可指定固定引擎；auto=智能路由：
    中文优先秘塔(每天100分可持续)→博查，英文用Tavily（爸爸2026-08-25定）。"""
    count = _count()
    engine = str(_search_setting("engine", "auto"))
    if engine == "metaso":
        return "【秘塔中文】\n" + _metaso(query, count)
    if engine == "bocha":
        return "【博查中文】\n" + _bocha(query, count)
    if engine == "tavily":
        return "【Tavily英文】\n" + _tavily(query, count)
    if engine == "searxng":
        return "【SearXNG】\n" + _searxng(query, count)
    # auto 智能路由
    has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in query)
    try:
        if has_cjk:
            try:
                return "【秘塔中文】\n" + _metaso(query, count)
            except Exception:
                return "【博查中文(秘塔失败回退)】\n" + _bocha(query, count)
        return "【Tavily英文】\n" + _tavily(query, count)
    except Exception as e:
        try:
            res = _tavily(query) if has_cjk else _bocha(query)
            return res
        except Exception as e2:
            return f"搜索失败: {e2}"


if __name__ == "__main__":
    # 自测
    print("===== 测试博查(中文) =====")
    print(web_search_bocha("DeepSeek V4 发布"))
    print("\n===== 测试Tavily(英文) =====")
    print(web_search_tavily("deepagents langchain"))
    print("\n===== 测试通用自动 =====")
    print(web_search("哪吒2 票房"))
