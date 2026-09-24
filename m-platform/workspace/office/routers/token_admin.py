"""
office.routers.token_admin —— /settings/token（status/首设注册/轮换/清除）+ /auth/*（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。
R10.408（爸爸 09-23 令："没注册之前不该上锁，注册之后才上锁"+"管理员必须有名字"）：
- 激活码（bootstrap）机制整体废除——未配置态=注册窗口开放，谁先注册谁是主人；
- 注册页直接设【用户名+密码】，用户名落 general.admin_name（登录双要素自此有真名）；
- 防护残余：X-Guard-Key（office↔guard 通信钥匙，沙箱没有）+ 各端点分桶限频 + 全程审计 IP。
注：_token_audit / _presented_token 下沉 core.py——前者被 misc 的 /approvals 复用，后者被 app.py 守卫复用。
路由注册顺序：本模块必须在 providers 之前 include——POST /settings/token（实名路由）必须抢在
POST /settings/{section}（路径参数）之前，否则首设/轮换会被 {section} 吞掉（原源码序 :1333 早于 :1633）。
"""
import time
import urllib.error  # 原 :16
import secrets as _secrets  # 原 :1159

from fastapi import APIRouter, Body, Request

from settings_mgr import (clear_verify_cache, get_api_token, api_token_configured, set_api_token,
                          token_ok as _token_ok, M_GUARD_URL, _guard_post,
                          load_settings, save_section)  # 原 :1161；r27 P1：守卫通道收敛单一来源（os 随旧 urllib 裸调用一并退役）；r29：档位专端点

from ..core import _JSONResp, _RawResp, _presented_token, _token_audit

router = APIRouter()

_BOOT_BUCKETS: dict = {"register": [], "clear": [], "login": [], "rotate": []}  # R10.7b（hy4 P1-4）：按用途分桶（r27 若若 P3-1：bootstrap 桶名改 register，防复活 grep 面清零）


def _boot_rate_ok(purpose: str = "register") -> bool:
    """R10.2（hy4 ②-7）+R10.7b 分桶：首设/清除/登录/轮换各用各的窗口（60s≤10）——
    陌生登录流量不再把爸爸自己的首设/清除一起 429。未配置态的 DELETE 也限频。"""
    hits = _BOOT_BUCKETS.setdefault(purpose, [])
    now = time.time()  # 原 :1229
    while hits and now - hits[0] > 60.0:
        hits.pop(0)
    if len(hits) >= 10:
        return False
    hits.append(now)
    return True


def _valid_username(u: str) -> bool:
    """R10.408：注册用户名=2~32 字符、拒全部控制字符（r27 评审 P2-6：旧黑名单只列 4 个
    字符，\x01/RTL 覆盖符等照样能进——改 ord 判定；显示与比对都走 strip 后原样）。"""
    return 2 <= len(u) <= 32 and not any(ord(c) < 32 or ord(c) == 127 for c in u)


# r27 评审 P1（Cora/Eve 独立同锤 + NOVA P1-② 根修）：本文件此前自带一份 _guard_url 白名单，
# 与 settings_mgr 的四个扇出点分叉——白名单拒绝时返回 "" 会误入本地分支=no-op 假成功链。
# 现收敛：地址校验唯一真源在 settings_mgr（_guard_url_ok/GUARD_URL_ILLEGAL），
# 守卫请求一律走 settings_mgr._guard_post；非法地址→raise→调用方 fail-closed 503。


@router.get("/settings/token/status")
async def api_token_status():
    return {"configured": api_token_configured()}


@router.post("/settings/token")
async def api_token_rotate(req: dict = Body(...), request: Request = None):
    """生成/轮换管理员密钥：已配置则必须带当前密钥（防被抢轮换锁死爸爸）；
    未配置（首设=注册）：R10.408 起无激活码——直接提交 username+password，
    谁先注册谁是主人；用户名落 general.admin_name（登录双要素的"名"由此而来）。
    返回新值【仅此一次】，前端种 HttpOnly Cookie。"""
    configured = api_token_configured()
    ip = (request.client.host if request and request.client else "?")
    guard = M_GUARD_URL
    if guard:
        # R10.6 守卫外置：密钥存取全走 m-guard（SYSTEM 常驻，明文不进本进程）。
        # R10.408：请求统一走 settings_mgr._guard_post（地址校验单一真源，非法=raise→503）。
        # 轮换证明=请求带来的当前钥匙；首设=注册窗口（限频+审计 IP 兜底）。
        import json as _rj
        current = _presented_token(request)
        payload = {"token": (req.get("token") or "").strip() or _secrets.token_hex(16)}
        uname = str(req.get("username") or "").strip()
        if configured:
            if not _boot_rate_ok("rotate"):  # R10.7b（hy4 P1-4）：轮换也纳入限频
                return _JSONResp({"error": "轮换过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
            payload["current"] = current
            if not current:
                _token_audit("rotate_denied", False, ip=ip)
                return {"ok": False, "error": "轮换管理员密钥需当前密钥"}
            # R10.8b（红队 P2①）：rotate 不再接受 password——改密码唯一通道=/auth/set_password
            # （需旧密码验证），防"持 Cookie 的脚本绕过旧密码校验覆盖找回通道"。
        else:
            if not _boot_rate_ok("register"):
                return _JSONResp({"error": "注册尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
            if not _valid_username(uname):
                return _JSONResp({"ok": False, "error": "用户名需 2-32 个字符"}, status_code=400)
            pwd = str(req.get("password") or "")
            if len(pwd) < 8:
                return _JSONResp({"ok": False, "error": "密码至少 8 位"}, status_code=400)
            payload["password"] = pwd
            # r27 评审 P3（Cora）：先落 admin_name 再写密钥——名字落不上就中止注册
            # （注释"失败要出声"必须与实现一致：此前是保存失败+ok:True 静默，
            # 爸爸会被默认名挡在门外）。名字先落而密钥后写失败=注册窗口仍开，重试覆盖，无害。
            try:
                from settings_mgr import save_section as _ss
                _ss("general", {"admin_name": uname})
            except Exception as e:
                _token_audit("admin_name_save_failed", False, err=type(e).__name__)
                return _JSONResp({"ok": False, "error": "用户名保存失败，注册已中止——请重试"}, status_code=500)
        try:
            result = _guard_post("/set", payload, timeout=8.0)
        except urllib.error.HTTPError as e:
            try:
                result = _rj.loads(e.read())
            except Exception:
                result = {"ok": False, "error": "被守卫拒绝"}
        except Exception as e:
            _token_audit("guard_error", False, err=type(e).__name__)
            return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)
        if not result.get("ok"):
            _token_audit("rotate_denied" if configured else "first_set_denied", False, ip=ip)
            return _JSONResp({"ok": False, "error": result.get("error", "被守卫拒绝")}, status_code=403)
        val = payload["token"]
        clear_verify_cache()  # R10.11（Eve P3）：rotate/首设成功即清验证缓存，30s 撤销窗口压到 0
        _token_audit("first_set" if not configured else "rotate", True, ip=ip)
        resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
        resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                        max_age=30 * 24 * 3600, path="/")
        return resp
    # 非 guard 模式继续走本地文件逻辑（本地裸跑兼容）
    if configured:
        if not _token_ok(_presented_token(request)):
            _token_audit("rotate_denied", False, ip=ip)
            return {"ok": False, "error": "轮换管理员密钥需当前密钥"}
    else:
        # R10.408：本地模式首设=注册窗口（用户名+密码），与 guard 模式同语义。
        if not _boot_rate_ok("register"):
            return _JSONResp({"error": "注册尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
        uname = str(req.get("username") or "").strip()
        if not _valid_username(uname):
            return _JSONResp({"ok": False, "error": "用户名需 2-32 个字符"}, status_code=400)
        if len(str(req.get("password") or "")) < 8:
            return _JSONResp({"ok": False, "error": "密码至少 8 位"}, status_code=400)
        val = (req.get("token") or "").strip() or _secrets.token_hex(16)
        # r30 Cora#6：与 guard 分支对称——先落名、落不上即中止（此时密钥未写、
        # 注册窗口仍开，重试无害）。此前顺序 set_api_token 在前：名字落库失败
        # 只审计不中止=密钥已上锁而 admin_name 缺位，爸爸下次登录输自设名
        # → _want 回落 "admin" 不匹配 → 被自己的名字挡在门外且无提示。
        try:
            from settings_mgr import save_section as _ss
            _ss("general", {"admin_name": uname})
        except Exception as e:
            _token_audit("admin_name_save_failed", False, err=type(e).__name__)
            return _JSONResp({"ok": False, "error": "用户名保存失败，注册已中止——请重试"}, status_code=500)
        set_api_token(val)
        _token_audit("first_set", True, ip=ip)
        resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
        resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                        max_age=30 * 24 * 3600, path="/")  # R10.5 XSS L2：JS 读不到的浏览器凭证
        return resp
    val = (req.get("token") or "").strip() or _secrets.token_hex(16)
    set_api_token(val)
    clear_verify_cache()  # R10.11（Eve P3）：本地模式轮换即时生效
    _token_audit("rotate", True, ip=ip)
    resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
    resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")
    return resp


# ── R10.7（爸爸："发布到 GitHub，没基础的用户怎么取得管理员权限"）：密码注册+找回 ──
# 注册向导（前端 SetupWizard，未配置时全屏展示）：激活码+设密码；
# 忘记 Cookie → /auth/login 输密码 → 换回密钥并种 Cookie（密码持有者=管理员，语义等价找回）。
@router.post("/auth/set_password")
async def auth_set_password(req: dict = Body(...), request: Request = None):
    """设置管理员密码：浏览器路径证明=旧密码（r27 评审 P1-1 收紧，当前密钥不再代转）；
    宿主直连 guard 的救急通道（reset_password.cmd）另走物理信任锚，不经本端点。"""
    guard = M_GUARD_URL
    # R10.11（千问）：/auth/set_password 此前 office 侧无限频（guard 侧有 10/min 但每次拒绝仍落守卫审计行）——补同款分桶
    if not _boot_rate_ok("setpwd"):
        return _JSONResp({"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    if not guard:
        return _JSONResp({"ok": False, "error": "本地裸跑模式不支持（未配置守卫）"}, status_code=503)
    # r27 评审 P1-1（CB 发现，知夏核实）：浏览器路径只认【旧密码】——不再把请求带来的
    # 当前密钥转手当证明。否则持 Cookie 的 XSS 脚本（读不到 HttpOnly 但发得出同源请求）
    # 可无旧密码改密、把真主人的找回通道换锁——正是 R10.8b 要堵的洞在此端点的复发。
    # 宿主救急通道 reset_password.cmd 直连 guard（物理访问=信任锚），不经本层、不受影响。
    payload = {"password": str(req.get("password") or "")}
    old_pwd = str(req.get("old_password") or "")
    if old_pwd:
        payload["old_password"] = old_pwd  # R10.8d：改找回密码必须验旧密码
    try:
        result = _guard_post("/set_password", payload, timeout=8.0)
        return _JSONResp(result, status_code=200 if result.get("ok") else 403)
    except urllib.error.HTTPError as e:
        # R10.8d：守卫的 403/429（密码太短/旧密码不符/限频）透传真实原因，不再谎报"不可达"
        try:
            _body = e.read()
        except Exception:
            _body = b'{"ok": false}'
        return _RawResp(_body, status_code=e.code, media_type="application/json")
    except Exception as _e:
        return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)


@router.post("/auth/login")
async def auth_login(req: dict = Body(...), request: Request = None):
    """密码找回登录：验证通过即种 Cookie 并返回密钥（仅此一次显示）。"""
    guard = M_GUARD_URL
    if not guard:
        return _JSONResp({"ok": False, "error": "本地裸跑模式不支持（未配置守卫）"}, status_code=503)
    if not _boot_rate_ok("login"):
        return _JSONResp({"error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    # 09-17 OWUI 颗粒度对齐（爸爸令"登录名+登录密码"双要素）：登录名=注册时爸爸亲手
    # 所设（R10.408 起注册向导必填），存 general.admin_name、设置页可改；未注册过的
    # 老装默认 "admin"。不匹配=与密码错同款泛化报错，不透露哪个错了
    # （OWUI "Incorrect email or password" 同款），不打到 guard 不占失败锁。
    from settings_mgr import load_settings as _ls
    _want = str((_ls().get("general", {}) or {}).get("admin_name") or "admin").strip()
    if str(req.get("username") or "").strip() != _want:
        # r27 评审 P2-2（CB）：用户名不匹配此前零审计——补一行（不打 guard 不占失败锁的
        # 设计保留：本地单管理员场景时序侧信道价值极低，审计补齐即够）。
        _token_audit("login_name_mismatch", False, ip=(request.client.host if request and request.client else "?"))
        return _JSONResp({"ok": False, "error": "登录名或密码不正确"}, status_code=200)
    import json as _lj
    import urllib.error as _lue  # R10.8c：区分"守卫拒绝（HTTPError 透传真实原因）"与"守卫不可达（503）"
    try:
        result = _guard_post("/login", {"password": str(req.get("password") or "")}, timeout=8.0)
    except urllib.error.HTTPError as e:
        # R10.8d：login 的 403/429（密码不符/锁定/未设密码）透传真实原因。
        # R10.11（Eve）：改 _RawResp 原样透传——旧写法把守卫 JSON 塞进 {"error": "<json字符串>"} 双层
        # 包装，前端拿到一坨转义串（对照同文件 set_password 的正确写法）。
        try:
            _body = e.read()
        except Exception:
            _body = b'{"ok": false}'
        return _RawResp(_body, status_code=e.code, media_type="application/json")
    except Exception as _e:
        return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)
    if not result.get("ok"):
        # 09-17 OWUI 同款泛化：密码错与登录名错同一句文案（锁定/未设密码等运维信息保留原样）
        if str(result.get("error") or "") == "密码不正确":
            result = {"ok": False, "error": "登录名或密码不正确"}
        return _JSONResp(result, status_code=200)
    val = result["token"]
    # r27 评审 P2-3（CB）：guard /login 已 rotate 重签发新钥，office 的 30s 验证缓存里
    # 旧钥还能顶 30 秒——登录成功即清缓存，撤销窗口压到 0（与 rotate 端点对称）。
    clear_verify_cache()
    _token_audit("login_password", True, ip=(request.client.host if request and request.client else "?"))
    # R10.8d（爸爸被挤掉线 N 次的教训）：office 层不做第二次轮换——rotate 发生在 guard /login 内
    # （重签发新密钥，千问 P0-1：找回不回吐旧明文），本端点只把【新密钥】种进 HttpOnly Cookie，
    # 明文不经响应体。对单浏览器用户无感（立即拿到新 Cookie）；旧 Cookie/旧 hostcopy 同时作废
    # （hostcopy 由 guard _write_token 同步刷新，m-gates 不受影响）。
    # 测试密码请用 guard /verify_password（只验不签发，绝不触发本链路）。
    resp = _JSONResp({"ok": True, "note": "登录成功（Cookie 已种入）"})
    resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")
    return resp


@router.delete("/settings/token")
async def api_token_clear(request: Request = None):
    """清除管理员密钥（回到未配置=注册窗口重新开放）。需当前密钥。用于爸爸彻底重置。
    R10.408：清除后不再重建激活码——注册流程已反转为"谁先注册谁是主人"。
    R10.2（hy4 ②-7）：未配置态的 DELETE 限频（防洪水 IO）。"""
    if not _boot_rate_ok("clear"):
        return _JSONResp({"error": "密钥管理操作过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    guard = M_GUARD_URL
    if guard:
        # R10.6：清除走守卫（guard 验当前密钥+清 DPAPI）。
        import json as _cj
        payload = {"token": _presented_token(request)}
        try:
            result = _guard_post("/clear", payload, timeout=8.0)
        except urllib.error.HTTPError as e:
            # R10.8c：HTTP 层拒绝（403/429）透传守卫的真实原因；连接层失败才报"不可达"
            try:
                _body = e.read()
            except Exception:
                _body = b'{"ok": false}'
            return _RawResp(_body, status_code=e.code, media_type="application/json")
        except Exception as _e:
            print(f"[auth] clear 异常: {type(_e).__name__}: {_e}", flush=True)
            return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)
        if not result.get("ok"):
            return _JSONResp(result, status_code=403)
        _token_audit("token_clear", True, ip=(request.client.host if request and request.client else "?"))
        clear_verify_cache()  # R10.11（Eve P3）：清除密钥=撤销即时生效，不等 30s TTL
        resp = _JSONResp({"ok": True, "cleared": True})
        resp.delete_cookie("m_admin_token", path="/")
        return resp
    if api_token_configured() and not _token_ok(_presented_token(request)):
        return {"ok": False, "error": "清除需当前密钥"}
    ip = (request.client.host if request and request.client else "?")
    set_api_token("")
    clear_verify_cache()  # R10.11（Eve P3）：本地模式清除同样即时撤销
    _token_audit("token_clear", True, ip=ip)
    resp = _JSONResp({"ok": True, "cleared": True})
    resp.delete_cookie("m_admin_token", path="/")  # R10.5：清除=浏览器 Cookie 一并作废
    return resp


# ── r29 焊档：确认分档专用端点（爸爸 09-24 令 + Cora/Veda/若若三家判词独立收敛：方向性人证）──
# 语义：plan<strict<auto_edit<full；新档比现档【宽松】→ 必须管理员密码验证
# （guard /verify_password：只验不发、零轮换、与登录同桶 5 败锁=防爆破白送；
#  共桶是知情代价：持 token 者连错 5 次会把 /login 找回通道锁 300 秒——可逆，r30 CB#1 接受）；
# 【收紧】方向自由（紧急刹车不设门槛——Veda：权限方向做非对称设计）。
# 通用 /settings/general 的 confirmLevel 路径已在 providers.py 同批关闭，HTTP 层无旁路
# （full 档宿主执行面=「米娅=知夏同等权限」定纲的 by-design 代价，r30 CB#4 在案）。
# 专审记录：confirm_level_change（旧→新+是否放宽+验证结果+IP）落 **office 侧账本
# D:\m\secrets\token_audit.jsonl**（r30 CB#3 措辞更正——守卫自己的账本在
# D:\m\guard\token_audit.jsonl，两本同名，取证勿混）。
_TIER_RANK = {"plan": 0, "strict": 1, "auto_edit": 2, "full": 3}


@router.post("/settings/confirm-level")
async def api_set_confirm_level(req: dict = Body(...), request: Request = None):
    # r30 CB#5（glm-5.3 复测）：office 侧限频桶——此前 missing_password 路径不出守卫、
    # 不限频，持 token 者可全速刷审计账本（10MB×5 代旋转把既有证据挤出窗口）。
    if not _boot_rate_ok("confirlvl"):
        return _JSONResp({"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    ip = (request.client.host if request and request.client else "?")
    new = str(req.get("level") or "").strip()
    if new not in _TIER_RANK:
        return _JSONResp({"ok": False, "error": "非法档位（四档：plan/strict/auto_edit/full）"}, status_code=400)
    # r30 CB#7 原子性注记：放宽判定「读档→验密→落盘」全靠本 handler 同步无 await
    # （守卫调用是阻塞 urllib）保证原子——日后在判档与落盘之间插入任何 await，即开
    # 「full→full no-op 与管理员收紧并发」的无密升档竞态。动这条链=先重读这段注记。
    # r30 Veda F9：general 节若被写坏成非 dict，.get 直接 AttributeError→500；
    # 防御性 isinstance——坏数据按"未设置"回落 strict（与 _level() fail-closed 同族）。
    _g = load_settings().get("general")
    cur = str(_g.get("confirmLevel") or "strict") if isinstance(_g, dict) else "strict"
    if cur not in _TIER_RANK:
        cur = "strict"  # 与后端 _level() 同款 fail-closed 回落
    relaxed = _TIER_RANK[new] > _TIER_RANK[cur]
    if relaxed:
        pwd = str(req.get("password") or "")
        if not pwd:
            _token_audit("confirm_level_change", ok=False, reason="missing_password", cur=cur, new=new, ip=ip)
            return _JSONResp({"ok": False, "need_password": True,
                              "error": "放宽档位需管理员密码验证（收紧不需要）"}, status_code=403)
        try:
            v = _guard_post("/verify_password", {"password": pwd}, timeout=8.0)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # r30 CB#6：守卫限频/5 败锁≠密码错——如实分译（schtasks 谎报案同族）。
                _token_audit("confirm_level_change", ok=False, reason="guard_ratelimited", cur=cur, new=new, ip=ip)
                return _JSONResp({"ok": False,
                                  "error": "验证服务限频中（连续失败会触发 300 秒锁定），5 分钟后再试"}, status_code=429)
            v = {"ok": False}
        except Exception:
            # 守卫不可达=fail-closed：放宽方向绝不盲放（收紧不受影响，见下）
            return _JSONResp({"ok": False, "error": "守卫不可达（fail-closed），稍后再试"}, status_code=503)
        if not v.get("ok"):
            _token_audit("confirm_level_change", ok=False, reason="bad_password", cur=cur, new=new, ip=ip)
            return _JSONResp({"ok": False, "error": "密码验证失败"}, status_code=403)
    save_section("general", {"confirmLevel": new})
    # r30 CB#2：审计失败=回滚——放宽不许无痕生效（此前 _token_audit 吞异常，
    # secrets 卷不可写时档位变更不留痕；观测面静默=爸爸之恨 schtasks 同族）。
    try:
        _token_audit("confirm_level_change", ok=True, cur=cur, new=new, relaxed=relaxed, ip=ip, strict=True)
    except Exception as e:
        try:
            save_section("general", {"confirmLevel": cur})
            _token_audit("confirm_level_change_rollback", ok=True, cur=new, new=cur, ip=ip)
        except Exception:
            _token_audit("confirm_level_change_rollback", ok=False, reason=type(e).__name__, cur=new, new=cur, ip=ip)
        return _JSONResp({"ok": False, "error": "审计日志写入失败，放宽已回滚，请排查 secrets 卷后重试"}, status_code=503)
    return {"ok": True, "confirmLevel": new, "previous": cur}
