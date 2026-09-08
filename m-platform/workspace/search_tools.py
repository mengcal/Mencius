# -*- coding: utf-8 -*-
"""工人岗搜索工具：博查(中文) + Tavily(英文)，供 deepagents 挂载
用法：tools=[web_search_bocha, web_search_tavily, web_search]
"""
import json, urllib.request, urllib.parse

# 密钥管理（管理员铁律：不硬编码）：一律从 settings_mgr（设置页"联网搜索"可自由改）读取，
# 没配置 = 返回未配置提示，绝不写死任何密钥（2026-08-29 应管理员要求删除全部兜底常量）。
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


BOCHA_URL = "https://api.bochaai.com/v1/web-search"
TAVILY_URL = "https://api.tavily.com/search"
METASO_URL = "https://metaso.cn/api/mcp"
SEARXNG_URL = "http://searxng:8080/search"
BING_URL = "https://www.bing.com/search"


def _count() -> int:
    """搜索结果数量（设置页可改，默认 5）"""
    try:
        return int(_search_setting("resultCount", 5))
    except Exception:
        return 5


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
    req = urllib.request.Request(BOCHA_URL, data=body, headers={
        "Authorization": f"Bearer {_key('bochaKey')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    # 兼容两种返回格式
    pages = d.get("data", {}).get("webPages", {}).get("value", []) if isinstance(d.get("data"), dict) else []
    if not pages:
        pages = d.get("results", []) or d.get("data", {}).get("results", []) if isinstance(d.get("data"), dict) else []
    return _fmt(pages)


def _mcp_call(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(METASO_URL, data=body, headers={
        "Authorization": f"Bearer {_key('metasoKey')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def _metaso(query, count=5):
    # 秘塔 MCP 搜索，扣积分（约3分/次，每天100分）
    if not _key("metasoKey"):
        return _no_key("秘塔")
    d = _mcp_call("tools/call", {"name": "metaso_web_search",
        "arguments": {"q": query, "size": count, "scope": "webpage", "includeSummary": True}})
    text = ""
    for c in d.get("result", {}).get("content", []):
        if c.get("type") == "text":
            text += c.get("text", "")
    try:
        data = json.loads(text)
        credits = data.get("credits", "?")
        pages = data.get("webpages", [])
        out = []
        for p in pages[:count]:
            title = p.get("title", "")
            link = p.get("link", "")
            snip = (p.get("snippet", "") or "")[:150]
            out.append(f"- {title}\n  链接: {link}\n  摘要: {snip}")
        return f"(扣{credits}分)\n" + ("\n".join(out) if out else "（无结果）")
    except Exception:
        return "（秘塔返回异常）" + text[:200]


def _searxng(query, count=5):
    import urllib.parse
    base = str(_search_setting("searxngUrl", SEARXNG_URL)).rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        base = SEARXNG_URL.rstrip("/")  # R10.11（评审E P2-4）：轻闸门——异 scheme（file:/data: 等）回落默认内网 searxng；
                                        # 不套 providers 的公网闸门是因为默认值本来就是容器内网地址（设计如此）
    lang = str(_search_setting("searxngLang", "all"))
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


def _bing(query, count=5):
    """必应(cn.bing.com)免代理搜索，解析HTML标题+链接。"""
    q = urllib.parse.quote(query)
    url = f"{BING_URL}?q={q}&setlang=zh-hans&count={count}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=15) as r:
        content = r.read().decode("utf-8", "ignore")
    out = []
    # 必应结果结构: <li class="b_algo">...<h2><a href="URL">标题</a></h2>...<p>摘要</p>
    for block in re.split(r'<li class="b_algo"', content)[1:count + 1]:
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        link = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2))
        title = _html.unescape(title).strip()
        snip_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        snip = re.sub(r'<[^>]+>', '', snip_m.group(1)) if snip_m else ""
        snip = _html.unescape(snip).strip()[:150]
        out.append(f"- {title}\n  链接: {link}\n  摘要: {snip}")
    return "\n".join(out) if out else "（无结果或需重试）"


def _tavily(query, count=5):
    if not _key("tavilyKey"):
        return _no_key("Tavily")
    body = json.dumps({"api_key": _key("tavilyKey"), "query": query, "max_results": count}).encode()
    req = urllib.request.Request(TAVILY_URL, data=body, headers={"Content-Type": "application/json"})
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


def web_search_searxng(query: str) -> str:
    """SearXNG搜索（本地免费无限，广撒网）。返回标题、链接、摘要。"""
    try:
        return _searxng(query)
    except Exception as e:
        return f"SearXNG搜索失败: {e}"


def web_search_bing(query: str) -> str:
    """必应搜索（免代理，cn.bing.com可用）。返回标题、链接、摘要。"""
    try:
        return _bing(query)
    except Exception as e:
        return f"必应搜索失败: {e}"


def web_search(query: str) -> str:
    """通用搜索。设置页 search.engine 可指定固定引擎；auto=智能路由：
    中文优先秘塔(每天100分可持续)→博查，英文用Tavily（管理员2026-08-25定）。"""
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
                return "【秘塔中文】\n" + _metaso(query)
            except Exception:
                return "【博查中文(秘塔失败回退)】\n" + _bocha(query)
        return "【Tavily英文】\n" + _tavily(query)
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
