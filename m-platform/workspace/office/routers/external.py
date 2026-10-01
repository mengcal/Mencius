# -*- coding: utf-8 -*-
"""office/routers/external.py —— 对外派活一期（r58，圆桌方案 v3 §三-4）。

边界（一期）：外部岗=本机环回 webhook（CodeBuddy 岗化），公网外部=二期 A2A。
登记走 token 门（爸爸权柄）；派活走 C1 批准卡（一条批准覆盖派活动作本身）；
回调带 HKDF 子钥（一岗一钥，泄露只伤单岗；master 存平台加密 secrets 存储，
走 secret_get——运行时不落密钥文件）；产出回传经 approvals.external_store 并入
批准账（ev=external_result，米娅 list_external_results 抽检核验再呈报）。
"""
import hmac

from fastapi import APIRouter, Body, Request

router = APIRouter()

from ..core import _token_audit  # 与 misc 同源（相对导入——绝对 core 不在 sys.path）


def _posts_load() -> dict:
    from settings_mgr import load_settings
    return load_settings().get("external_posts") or {}


_POSTS_LOCK = __import__("threading").Lock()
_REPLAY_SEEN: dict = {}  # r61d P1-4（hy4）：{tid: set(ts)}——每 tid 只记一个 ts 的话，
                        # 600s 窗口内递增 ts 即无限重放；改集合，同 tid 同 ts 才拒


def _replay_prune():
    if len(_REPLAY_SEEN) > 500:
        for k in list(_REPLAY_SEEN)[:250]:
            _REPLAY_SEEN.pop(k, None)


def _posts_mutate(mut):
    """r61c N16（hy4 二轮）：整段"新鲜读+变更+原子落"锁内完成——旧版 load 在锁外、
    save 里重读又拿旧快照覆盖回去，读-改-写竞态根本没关死（注释过claim 的又一案）。
    mut(posts)->返回值；mut 内不落写，写由本函数统一原子做。"""
    import json
    from settings_mgr import load_settings, save_section
    with _POSTS_LOCK:
        s = load_settings()
        posts = s.get("external_posts") or {}
        r = mut(posts)
        # r34（CB 2.2 P1）：第三写者收编——原 tmp+os.replace 在容器内 :ro 根必炸
        # （r30 已实证），且绕过 .bak/_rev/敏感键隔离。统一走 save_section。
        save_section("external_posts", posts)
        return r


@router.post("/external/register")
async def external_register(req: dict = Body(...), request: Request = None):
    """登记外部岗：{name, url, ports:[int], overwrite?:true}。SSRF v3 校验（解析+钉 IP）。
    r61b P2-3（hy4）：同名登记必须显式 overwrite——静默覆盖=岗劫持面
    （别人抢注你的岗名，回调全进他口袋）。存在性检查也在锁内（TOCTOU）。
    r40g：私网来源（内器官）登记免 SSRF 校验——url 只是内部标识。"""
    from mia_agent.external_guard import validate_url, ExternalUrlError
    name = str(req.get("name") or "").strip()
    url = str(req.get("url") or "")
    try:
        ports = tuple(int(p) for p in (req.get("ports") or []))
    except (TypeError, ValueError):
        return {"ok": False, "error": "ports 必须是端口号列表（如 [9000]）"}
    # r40g（爸 07:20 裁决"n8n 是平台内器官不是外部岗"）：私网来源登记内器官岗
    # 免 SSRF 校验（自拉岗平台永不主动连它，url 只是内部标识；真外部岗照走全校验）。
    _family_reg = False
    try:
        import ipaddress as _ipa
        _fam_ip = _ipa.ip_address(request.client.host if request and request.client else "")
        _family_reg = _fam_ip.is_private or _fam_ip.is_loopback
    except ValueError:
        _family_reg = False
    if not name:
        return {"ok": False, "error": "name 必填"}
    if not _family_reg and (not url or not ports):
        return {"ok": False, "error": "name/url/ports 都必填（端口白名单爸爸手填）"}
    if not _family_reg:
        try:
            checked = validate_url(url, ports)
        except ExternalUrlError as e:
            _audit("external_register", False, name=name, why=str(e)[:80])
            return {"ok": False, "error": f"URL 校验拒绝：{e}"}
    else:
        checked = {"ip": "family", "host": url or "internal", "scheme": "internal"}

    def _mut(p):
        if name in p and not req.get("overwrite"):
            return "exists"
        p[name] = {"url": url, "ports": list(ports), "pin_ip": checked["ip"],
                   "host": checked["host"], "scheme": checked["scheme"]}
        return True
    r = _posts_mutate(_mut)
    if r == "exists":
        return {"ok": False, "error": f"岗 {name} 已存在——改地址须显式 overwrite=true"}
    _audit("external_register", True, name=name, ip=checked["ip"],
           overwrite=bool(req.get("overwrite")))
    return {"ok": True, "name": name, "pinned_ip": checked["ip"]}


@router.get("/external/list")
async def external_list():
    posts = _posts_load()
    return {"posts": [{"name": k, "url": v.get("url"), "ports": v.get("ports")}
                      for k, v in posts.items()]}


@router.delete("/external/register")
async def external_unregister(req: dict = Body(...)):
    name = str(req.get("name") or "")
    had = _posts_mutate(lambda p: p.pop(name, None)) is not None
    _audit("external_unregister", bool(had), name=name)
    return {"ok": bool(had)}


def _subkey_ok(name: str, auth: str) -> bool:
    """HKDF 子钥恒时比较（pending/callback 共用）。"""
    import hmac
    try:
        from mia_agent.external_guard import hkdf_subkey
        from settings_mgr import secret_get
        mk = (secret_get("external.master_key") or "").encode("utf-8")
        if not mk:
            return False
        return hmac.compare_digest(auth, hkdf_subkey(mk, name).hex())
    except Exception:
        return False


def _requester_is_family(request) -> bool:
    """r40g（爸 07:20 裁决）：n8n 等容器岗=平台**内器官**，不是'外部岗'——
    归米娅调派、西莉亚也有权限调派，'这才是私人平台的意义'。私网来源
    （Docker 内网容器/本机）跳过子钥检查，与 auth.py r40c 本机免钥同口径；
    子钥通道保留给真正的外部岗（公网回调型）。审计照落（family-source）。"""
    try:
        import ipaddress
        ip = ipaddress.ip_address(request.client.host if request and request.client else "")
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def _gate(name: str, request, ev: str) -> tuple[bool, str]:
    """r40g 统一放行口：私网=自家人免子钥；否则 HKDF 子钥。审计不缺页。"""
    if _requester_is_family(request):
        try:
            _audit(ev, True, name=name, why="family-source")
        except Exception:
            pass
        return True, "family"
    auth = (request.headers.get("authorization") or "").replace("Bearer ", "").strip()
    if _subkey_ok(name, auth):
        return True, "subkey"
    _audit(ev, False, name=name, why="bad-subkey")
    return False, "bad-subkey"


@router.get("/external/pending/{name}")
async def external_pending(name: str, request: Request):
    """取单预览（r61 NOVA P0-4 拆分）：纯读零副作用——监控/探测 GET 不再顺手
    领取饿死真岗。领单必须走 POST /external/claim（意图显式化）。
    r40g：内器官（私网容器/本机）免子钥直取。"""
    posts = _posts_load()
    if name not in posts:
        return {"ok": False, "error": "岗位未登记"}
    ok, _how = _gate(name, request, "external_pending")
    if not ok:
        return {"ok": False, "error": "子钥校验失败"}
    import approvals as _ap
    return {"ok": True, "tasks": _ap.external_pending_view(name)}


@router.post("/external/claim/{name}")
async def external_claim(name: str, request: Request):
    """显式领单：{task_id}。领取落账 external_claim（30 分钟无回执超时重投）。
    at-least-once 纪律：领了不交=该单挂到超时，岗脚本必须干活后回调或退单。
    r40g：内器官免子钥（_gate）。"""
    posts = _posts_load()
    if name not in posts:
        return {"ok": False, "error": "岗位未登记"}
    ok, _how = _gate(name, request, "external_claim")
    if not ok:
        return {"ok": False, "error": "子钥校验失败"}
    body = await request.json()
    tid = str((body or {}).get("task_id") or "")
    if not tid:
        return {"ok": False, "error": "task_id 必填"}
    import approvals as _ap
    # r61b P1-4：领取条件化——复核此刻仍可领，双岗并发只一个 True
    if not _ap.external_claim(name, tid):
        _audit("external_claim", False, name=name, why="not-claimable", tid=tid)
        return {"ok": False, "error": "该单不可领（已被领/已完成/退单超限）"}
    return {"ok": True, "claimed": tid}


def _callback_source(request) -> tuple:
    """r61e（Eve 护栏①②+Veda②③+Lyra"拓扑不可知"论）：返回 (ok, 来源分级)。
    - env MIA_EXTERNAL_SOURCES 已设 → **强制态**：环回 ∪ 精确 IP 列表（单 IP，禁网段
      写法——整段放行=同网容器冒充岗回调，Veda②/Eve①同判）。
    - env 未设 → **观测态**：环回+私网放行但来源分级落账（observed-bridge/observed-other）。
      收口条件（Veda③，防折中烂成永久方案）：连续 7 天只见网关 IP → 爸爸把观测到的
      具体 IP 填进 env 转强制态；期间出现**非网关容器 IP**=已被试探的信号，直接上报。
    监听面事实（Lyra①）：2024 发布口 compose 绑 127.0.0.1（R68），外部打不进来——
    本函数管的是容器网内来源分级，两层各自成立。
    台账口径（NOVA 晨卷钉）：本层是**拓扑过滤**不是"岗身份验证"——同宿主容器同走
    桥网关，真身份=HKDF 子钥；审计读账时别高估这层（措辞按此，勿写"身份"）。"""
    host = (request.client.host if request.client else "") or ""
    if host in ("localhost", "testclient"):
        return True, "loopback"
    try:
        import ipaddress
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False, "unparse"
    if ip.is_loopback:
        return True, "loopback"
    import os
    env = {h.strip() for h in (os.environ.get("MIA_EXTERNAL_SOURCES") or "").split(",")
           if h.strip()}
    if env:
        return (host in env), ("env-list" if host in env else "reject-enforce")
    if ip.is_private:
        # 桥网关=容器网默认网关（x.y.z.1/x.y.0.1 惯例）；其余私网 IP=同网邻居容器
        gw = host.endswith(".1")
        return True, ("observed-bridge" if gw else "observed-other")
    return False, "reject-public"


@router.post("/external/callback/{name}")
async def external_callback(name: str, request: Request):
    """外部岗回调：Authorization: Bearer <HKDF 子钥 hex> + 环回来源。验后并入批准账。"""
    import approvals as _ap
    posts = _posts_load()
    if name not in posts:
        return {"ok": False, "error": "岗位未登记"}
    # r61e：来源双态（观测/强制）+分级落账。Eve 护栏②：观测期出现非网关容器 IP
    # =被试探信号，单独落账醒目上报。N10 的 https 强制并入语义简化：_callback_source
    # 已拒掉一切非本机等效来源（reject-public/enforce），放行的都是本机等效——
    # 公网化时随二期 mTLS 整体重做，不留半截 https 分支误导。
    ok_src, cls = _callback_source(request)
    if not ok_src:
        _audit("external_callback", False, name=name,
               why=f"source-reject:{cls}:{(request.client.host if request.client else '?')}")
        return {"ok": False, "error": "回调来源被拒（分级见审计）"}
    if cls == "observed-other":
        _audit("external_callback", True, name=name, why="SOURCE-PROBE-WARN:邻居容器IP")
    # r40g：内器官（私网容器/本机）免子钥——n8n 岗线回传直通（真外部岗仍走子钥）
    import ipaddress as _ipa
    _fam = False
    try:
        _fam = _ipa.ip_address(request.client.host if request and request.client else "").is_private
    except ValueError:
        _fam = False
    if not _fam:
        auth = (request.headers.get("authorization") or "").replace("Bearer ", "").strip()
        if not _subkey_ok(name, auth):
            _audit("external_callback", False, name=name, why="bad-subkey")
            return {"ok": False, "error": "子钥校验失败"}
    body = await request.body()
    # r61b P1-17（hy4）：回调体硬上限 64KB——旧版无上限，大 body 直灌内存+账文件
    if len(body) > 65536:
        _audit("external_callback", False, name=name, why=f"body-too-large:{len(body)}")
        return {"ok": False, "error": "回调体超 64KB 上限"}
    import json as _json
    try:
        data = _json.loads(body)
    except Exception:
        return {"ok": False, "error": "非法 JSON"}
    data = data if isinstance(data, dict) else {"data": data}
    tid = str(data.get("task_id") or "")
    if not tid:
        # r61b P1-7：task_id 必传（缺=多结果共键碰撞，superseded 会误杀正常回执）
        return {"ok": False, "error": "task_id 必填"}
    # r61c N10：ts 必传（epoch 秒）±300s 窗口 + (tid,ts) 进程内查重=重放最低成本防线
    try:
        _ts = float(data.get("ts") or 0)
    except (TypeError, ValueError):
        _ts = 0.0
    import time as _t
    if not _ts or abs(_t.time() - _ts) > 300:
        _audit("external_callback", False, name=name, why="ts-window")
        return {"ok": False, "error": "ts 缺失或超 300s 窗口（岗脚本请带时间戳）"}
    if _ts in _REPLAY_SEEN.setdefault(tid, set()):
        _audit("external_callback", False, name=name, why="replay", tid=tid[:16])
        return {"ok": False, "error": "重复回执（同 tid 同 ts）"}
    _REPLAY_SEEN[tid].add(_ts)
    _replay_prune()
    ctx = _ap.external_task_ctx(name, tid)
    if not ctx["known"]:
        # r61b P2-4：单必须是派给本岗的——持子钥给任意 tid 伪造 done 的路封死
        _audit("external_callback", False, name=name, why=f"tid-not-owned:{tid[:16]}")
        return {"ok": False, "error": "task_id 不属本岗"}
    if not ctx["claimed"]:
        # r61e Cora N6：未领取的单不可能有回执——"假 done 让任务静默消失"的
        # 验收欺骗链（丢失在上游、检查在下游）在此断掉。
        _audit("external_callback", False, name=name, why=f"not-claimed:{tid[:16]}")
        return {"ok": False, "error": "该单未领取（先 claim 再回调）"}
    if ctx["nonce"] and str(data.get("nonce") or "") != ctx["nonce"]:
        # r61e Lyra②：一次性 nonce=不依赖网络拓扑的回调身份（旧单无 nonce 向后兼容）
        _audit("external_callback", False, name=name, why=f"nonce-mismatch:{tid[:16]}")
        return {"ok": False, "error": "nonce 不符"}
    _ap.external_store(name, data, task_id=tid)
    _audit("external_callback", True, name=name, done=bool(data.get("done")),
           src=request.client.host if request.client else "", cls=cls)
    return {"ok": True, "stored": True}


def _audit(ev, ok_flag, **kw):
    """审计走 core 现成件（与 misc 同纪律）。"""
    return _token_audit(ev, bool(ok_flag), **kw)
