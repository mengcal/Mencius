"""
office.routers.providers —— Settings API v1 + /providers* + /models/all + SSRF 闸门（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :1616-1661  settings_mgr 导入 + GET /settings + POST /settings/{section}
- :1663-1675  /providers/fetch_models 已删除说明（注释保留）+ GET /providers
- :1678-1728  _assert_public_fetch_target（SSRF 闸门）/ _fetch_models_async / _save_external_provider
- :1731-1896  POST /providers/add|rename|refresh|toggle|delete|update + GET /models/all

归属裁定：拆分方案里 misc 清单也列了 /models/all（重复项）。按数据归属定到本模块
（它读 external.providers[].models_cache，与 /providers* 同源），misc 不再注册，避免同路径双注册。

路由注册顺序：本模块必须在 token_admin 之后 include——POST /settings/token（token_admin 实名路由）
必须抢在 POST /settings/{section}（本模块路径参数路由）之前，见 app.py create_app。
"""
import httpx as _httpx  # 原 :1619

from fastapi import APIRouter, Body, Request

from settings_mgr import load_settings, save_section, get_plain_provider_key, mask_key  # 原 :1618

from ..core import BASE

router = APIRouter()


@router.get("/settings")
async def api_get_settings():
    """全量设置（key 均为打码值）。agents 节唯一真源 = settings.agents（配置页）。
    附带 _rev（settings.json 修改时间戳）：前端保存时回传，不匹配=后台被改过 → 拒绝保存（R42 防撞车）。"""
    s = load_settings()
    # agents 直接来自 settings.agents（配置页=唯一真源）；不再用 agents_config.json 覆盖显示
    try:
        s["_rev"] = int((BASE / "settings.json").stat().st_mtime)
    except Exception:
        pass
    return s

@router.post("/settings/{section}")
async def api_set_settings(section: str, data: dict = Body(...), request: Request = None):
    """按节保存设置。敏感键：明文→secrets+打码；打码值→原样保留。
    agents 节：直接存 settings.agents（配置页=唯一真源，R65 起不再写回 agents_config.json）。"""
    try:
        # R42 防撞车：前端带 _rev 时校验版本，文件在页面加载后被别人改过 → 拒绝，提示刷新
        expected_rev = data.pop("_rev", None)
        if expected_rev is not None:
            try:
                current_rev = int((BASE / "settings.json").stat().st_mtime)
                if int(expected_rev) != current_rev:
                    return {"ok": False, "conflict": True,
                            "error": "设置已被后台修改（作者/助手/其他对话刚动过），请刷新页面后重改"}
            except Exception:
                pass
        # 权限检查（评审B#3/评审A#4）：r25（管理员裁决）X-By 常数头作废——
        # /settings/* 写面从 R10 起由 api_token_guard token fail-closed 真守（助手无钥匙=中间件 401），
        # 旧 by!=admin 双锁是 R75 无统一 token 时代的遗产，零额外熵，拆掉不再演双保险。
        # miaManageAgents 对助手的约束在工具面（manage_departments 直写 settings_mgr+确认门），不依赖此处 HTTP 判定。
        # R75：confirmLevel 回归 settings.general（设置页/顶栏快切同一真源），统一 token 守写入（助手无 token 改不动）。
        # R79④拆假注释：R74 的"带外 :ro 文件地板（两路取严）"已随"设置页 supreme/政令必通"定调整体退役——
        # _level() 单源读 settings.general.confirmLevel，未配置/非法 fail-closed strict；MIA_TIER_FILE 死配置已从 compose 撤除。
        result = save_section(section, data)
        # agents 已由 save_section 深度合并进 settings.agents（配置页=唯一真源）；不再回写 agents_config.json
        return {"ok": True, "saved": section, "data": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── R68 P0（五路评审同锤）：/providers/fetch_models 已删除 ──
# 它拿"请求里的任意 base_url"发送"已存明文 key"=密钥外带正门；且前端从不调用（只用 refresh/add），纯死攻击面。
# 拉模型一律走 _fetch_models_async（只认已登记地址，带 SSRF 闸门）。

@router.get("/providers")
async def api_providers():
    """统一服务商表：providers.json（遗留）+ 设置页外部连接（enabled 过滤）。
    Sub-agents 页下拉框数据源——工人岗 provider 就填这里的 key。"""
    from providers import load_providers
    return {"providers": [
        {"key": k, "model": v.get("model", "")}
        for k, v in load_providers().items()
    ]}


def _assert_public_fetch_target(url: str) -> str:
    """R68 SSRF 闸门（评审 A 面 + mimosa 验收）：拉模型只许 http/https、主机必须解析为公网 IP；
    拒环回/私有/链路本地/保留/组播（云元数据 169.254.x 同被拒）。本地模型请走 Ollama 通道，
    不当服务商挂——宁报错不越权。"""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("只允许 http/https 地址")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValueError(f"地址解析失败：{u.hostname}")
    for _fam, _, _, _, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"目标解析到非公网地址（{ip}）——模型拉取只允许公网服务商，宁报错不越权")
    return url


async def _fetch_models_async(name: str, base_url: str) -> list:
    """拉取服务商模型列表（add/refresh 共用）。在 FastAPI 事件循环内直接 await，
    绝不能用 asyncio.run()（事件循环里再开循环必崩，2026-08-29 踩坑）。
    R68：只允许 http/https + 公网 IP（_assert_public_fetch_target），防 SSRF/密钥外带。"""
    _assert_public_fetch_target(base_url)
    from settings_mgr import get_plain_provider_key
    key = get_plain_provider_key(name)
    async with _httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{base_url.rstrip('/')}/models",
                             headers={"Authorization": f"Bearer {key}"} if key else {})
        r.raise_for_status()
        return [m.get("id") for m in r.json().get("data", []) if m.get("id")]


def _save_external_provider(name: str, base_url: str, api_key: str = "", enabled: bool = True, models_cache=None):
    """把服务商写进 settings 的 external.providers（save_section 负责明文key隔离+打码）。"""
    s = load_settings()
    providers = s.get("external", {}).get("providers", [])
    entry = next((p for p in providers if p.get("name") == name), None)
    if entry is None:
        entry = {"name": name}
        providers.append(entry)
    entry["base_url"] = base_url
    entry["enabled"] = enabled
    if api_key:
        entry["api_key"] = api_key  # 明文，save_section 会转存 secrets 并打码
    if models_cache is not None:
        entry["models_cache"] = models_cache
    save_section("external", {"providers": providers})


@router.post("/providers/add")
async def api_provider_add(req: dict = Body(...)):
    """添加/更新服务商：{name, base_url, api_key} → 保存并自动拉取模型列表。
    管理员只要填地址和密钥，其他全自动（open-webui/sillytavern 同款体验）。"""
    name = (req.get("name") or "").strip()
    base_url = (req.get("base_url") or "").strip().rstrip("/")
    api_key = req.get("api_key") or ""
    if not name or not base_url:
        return {"error": "需要 name 和 base_url"}
    # R68 P0（评审 A 面）：换地址必须配新 key——杜绝"旧密钥静默发去新地址"的外带链
    _old = next((p for p in load_settings().get("external", {}).get("providers", []) if p.get("name") == name), None)
    if _old and not api_key and (_old.get("base_url") or "").rstrip("/") != base_url:
        return {"error": "地址已变更但没带新密钥——为防旧密钥被发往新地址，请重新粘贴该服务商的密钥再保存"}
    try:
        _save_external_provider(name, base_url, api_key)
        models = await _fetch_models_async(name, base_url)
        _save_external_provider(name, base_url, enabled=req.get("enabled", True), models_cache=models)
        return {"ok": True, "name": name, "count": len(models), "models": models}
    except Exception as e:
        return {"error": f"保存或拉取失败: {e}"}


@router.post("/providers/rename")
async def api_provider_rename(req: dict = Body(...)):
    """服务商改名（猪八戒也行）：{old, new}。
    联动同步：external.providers 条目、secrets 明文路径、agents_config.json 里引用它的工人岗。
    名字只是标签，引擎认的是名字背后的 base_url+key。"""
    old, new = (req.get("old") or "").strip(), (req.get("new") or "").strip()
    if not old or not new or old == new:
        return {"error": "需要 old 和 new（且不能相同）"}
    s = load_settings()
    providers = s.get("external", {}).get("providers", [])
    entry = next((p for p in providers if p.get("name") == old), None)
    if not entry:
        return {"error": f"服务商 {old} 不存在"}
    if any(p.get("name") == new for p in providers):
        return {"error": f"名字 {new} 已被占用"}
    entry["name"] = new
    # R74 回归修复（评审C P2-A）：save_section 的孤儿密钥清理会当场删掉旧名的 key，
    # 必须【先取旧 key】再保存、再把密钥落到新名——否则改名=密钥无声蒸发。
    from settings_mgr import secret_get, secret_set
    old_path, new_path = f"external.providers.{old}.api_key", f"external.providers.{new}.api_key"
    migrated = secret_get(old_path)
    # R79⑤：tombstone（曾有钥匙标记）随改名迁移——旧名被孤儿清理清账，先读后写
    old_flag, new_flag = f"external.providers.{old}.had_key", f"external.providers.{new}.had_key"
    migrated_flag = secret_get(old_flag)
    save_section("external", {"providers": providers})
    if migrated:
        secret_set(new_path, migrated)
    secret_set(old_path, "")
    if migrated_flag:
        secret_set(new_flag, "1")
    # 联动改工人岗引用
    changed = []
    try:
        # 联动改工人岗/组长/回退链引用：改的是配置页 settings.agents（唯一真源），不再碰 agents_config.json
        ag = load_settings().get("agents") or {}
        for k, a in ag.items():
            if isinstance(a, dict):
                if a.get("provider") == old:
                    a["provider"] = new
                    changed.append(k)
                for fb in (a.get("fallbacks") or []):
                    if isinstance(fb, dict) and fb.get("provider") == old:
                        fb["provider"] = new
                        if k not in changed:
                            changed.append(k)
        if changed:
            save_section("agents", ag)
    except Exception:
        pass
    return {"ok": True, "old": old, "new": new, "agents_updated": changed}


@router.post("/providers/refresh")
async def api_provider_refresh(req: dict = Body(...)):
    """重新拉取某服务商的模型列表：{name}"""
    name = req.get("name", "")
    s = load_settings()
    p = next((p for p in s.get("external", {}).get("providers", []) if p.get("name") == name), None)
    if not p:
        return {"error": f"服务商 {name} 不存在"}
    try:
        models = await _fetch_models_async(name, p.get("base_url", ""))
        _save_external_provider(name, p.get("base_url", ""), models_cache=models)
        return {"ok": True, "name": name, "count": len(models), "models": models}
    except Exception as e:
        return {"error": f"拉取失败: {e}"}


@router.post("/providers/toggle")
async def api_provider_toggle(req: dict = Body(...)):
    """启停服务商：{name, enabled}。停用后助手/工人岗立刻用不了它（load_providers 会过滤）。"""
    name = req.get("name", "")
    enabled = bool(req.get("enabled", True))
    s = load_settings()
    p = next((p for p in s.get("external", {}).get("providers", []) if p.get("name") == name), None)
    if not p:
        return {"error": f"服务商 {name} 不存在"}
    _save_external_provider(name, p.get("base_url", ""), enabled=enabled)
    return {"ok": True, "name": name, "enabled": enabled}


@router.post("/providers/delete")
async def api_provider_delete(req: dict = Body(...)):
    """删除服务商：{name}。从设置页移除（providers.json 遗留条目不受影响）。"""
    name = req.get("name", "")
    s = load_settings()
    providers = s.get("external", {}).get("providers", [])
    providers = [p for p in providers if p.get("name") != name]
    save_section("external", {"providers": providers})
    return {"ok": True, "name": name}


@router.post("/providers/update")
async def api_provider_update(req: dict = Body(...)):
    """编辑已存在服务商：{name, base_url?, api_key?, tag?, enabled?, mode?}。
    按名字定位、整表安全更新——绝不用 external.providers.<下标>.<字段> 点号路径
    （那会把 providers 列表写成 {"3":{...}} 字典，冲垮全部服务商；R41/本次崩溃同源 bug）。
    api_key 留空=保持不变；mode=chat_completions|anthropic|responses（open-webui/ZCode 三模式）。"""
    name = (req.get("name") or "").strip()
    if not name:
        return {"error": "需要 name"}
    s = load_settings()
    providers = s.get("external", {}).get("providers", [])
    entry = next((p for p in providers if p.get("name") == name), None)
    if entry is None:
        return {"error": f"服务商 {name} 不存在"}
    if req.get("base_url"):
        bu = req["base_url"].strip().rstrip("/")
        if not (bu.startswith("http://") or bu.startswith("https://")):
            return {"error": "base_url 必须是 http/https 地址"}
        # R71 补 R69 同源漏洞（自查所得）：换地址必须重带密钥——否则旧密钥经 refresh 被发往新地址（外带链）；
        # 新地址还须过 SSRF 闸门（公网 http/s），把坏地址拦在入库前。
        if bu != (entry.get("base_url") or "").rstrip("/") and not req.get("api_key"):
            return {"error": "地址已变更但没带新密钥——为防旧密钥被发往新地址，请重新粘贴密钥再保存"}
        try:
            _assert_public_fetch_target(bu)
        except ValueError as e:
            return {"error": str(e)}
        entry["base_url"] = bu
    if req.get("api_key"):
        entry["api_key"] = req["api_key"]  # 明文，save_section 转存 secrets 并打码
    if "tag" in req:
        entry["tag"] = req.get("tag") or ""
    if "enabled" in req:
        entry["enabled"] = bool(req.get("enabled"))
    if req.get("mode"):
        entry["mode"] = req["mode"]
    save_section("external", {"providers": providers})
    return {"ok": True, "name": name}


@router.get("/models/all")
async def api_models_all():
    """所有启用服务商的模型合集（工人岗下拉框数据源）。"""
    s = load_settings()
    out = []
    for p in s.get("external", {}).get("providers", []):
        if p.get("enabled", True):
            out.append({
                "provider": p.get("name"),
                "count": len(p.get("models_cache", [])),
                "models": p.get("models_cache", []),
            })
    return {"providers": out}
