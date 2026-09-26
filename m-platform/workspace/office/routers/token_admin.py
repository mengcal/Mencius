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
                          load_settings, save_section, settings_rev, BASE)  # 原 :1161；r27 P1：守卫通道收敛单一来源；r29：档位专端点；r30 NOVA F5：BASE 用于 _rev 防撞车；r32 CB F13：_rev 单源 settings_rev

from ..core import _JSONResp, _RawResp, _presented_token, _token_audit

router = APIRouter()

_BOOT_BUCKETS: dict = {"register": [], "clear": [], "login": [], "rotate": [], "setpwd": [], "logout": [], "confirm": []}  # R10.7b（hy4 P1-4）：按用途分桶（r27 若若 P3-1：bootstrap 桶名改 register，防复活 grep 面清零）；r32 F6：logout 补桶（此前全文件唯一没桶的端点）


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


# r32 F9（Qoder P2：后端黑话/英文错误原文直穿登录注册界面）——守卫与内部态的
# 错误文本一律经 _human_error 翻成爸爸能照做的人话；未知名回统一泛化句。
_GUARD_ERROR_ZH = {
    "missing guard key": "服务暂时不可用，请稍后再试",
    "token required": "服务暂时不可用，请稍后再试",
    "bad request": "请求格式不正确，请重试",
    "rate limited": "尝试过于频繁（60 秒内最多 10 次），稍后再试",
    "连续失败已锁定": "尝试次数过多，请 5 分钟后再试",
    "password not set": "登录名或密码不正确",  # 未设密码走注册，不向探测者确认状态
}


def _human_error(msg) -> str:
    s = str(msg or "").strip()
    low = s.lower()
    for k, v in _GUARD_ERROR_ZH.items():
        if k.lower() in low:
            return v
    if "fail-closed" in s or "裸跑" in s or "守卫服务不可达" in s or "守卫不可达" in s:
        return "服务暂时不可用，请稍后再试"
    if all(ord(c) < 128 for c in s) and s:  # 纯英文未知名=内部细节，一律泛化
        return "操作失败，请稍后再试"
    return s  # 中文人话原文放行


# r27 评审 P1（Cora/Eve 独立同锤 + NOVA P1-② 根修）：本文件此前自带一份 _guard_url 白名单，
# 与 settings_mgr 的四个扇出点分叉——白名单拒绝时返回 "" 会误入本地分支=no-op 假成功链。
# 现收敛：地址校验唯一真源在 settings_mgr（_guard_url_ok/GUARD_URL_ILLEGAL），
# 守卫请求一律走 settings_mgr._guard_post；非法地址→raise→调用方 fail-closed 503。


@router.get("/settings/token/status")
async def api_token_status():
    # r32 F5（CB 独家）：带 guard 标志——本地裸跑模式（无守卫）登录通道不存在，
    # 前端据此隐藏"退出登录"按钮，防"登出后永远登不回来"的自锁死路。
    # r32 F10（Qoder P2#9）：守卫不可达 ≠ 未配置——旧版两者都报 configured=false，
    # 把已注册管理员送进注册页（再注册必 503=往坑里引）。三态：探活失败→
    # configured 按已配置报+unreachable=True，前端显示"服务暂时不可用"页。
    if M_GUARD_URL:
        try:
            import json as _j
            import urllib.request as _u
            with _u.urlopen(f"{M_GUARD_URL}/status", timeout=5.0) as r:
                return {"configured": bool(_j.loads(r.read()).get("configured")),
                        "guard": True, "unreachable": False}
        except Exception:
            # fail-closed 的正确姿势：不开放注册窗口（防抢注竞态），显示不可用页
            return {"configured": True, "guard": True, "unreachable": True}
    return {"configured": api_token_configured(), "guard": False, "unreachable": False}


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
                # r32 F17（NOVA/Eve/Cora 三路同锤）：429 拒绝此前零审计=抢注尝试无痕
                _token_audit("rotate_rate_limited", False, ip=ip)
                return _JSONResp({"error": "轮换过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
            payload["current"] = current
            if not current:
                _token_audit("rotate_denied", False, ip=ip)
                return {"ok": False, "error": "轮换管理员密钥需当前密钥"}
            # R10.8b（红队 P2①）：rotate 不再接受 password——改密码唯一通道=/auth/set_password
            # （需旧密码验证），防"持 Cookie 的脚本绕过旧密码校验覆盖找回通道"。
        else:
            if not _boot_rate_ok("register"):
                _token_audit("register_rate_limited", False, ip=ip)  # r32 F17
                return _JSONResp({"error": "注册尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
            if not _valid_username(uname):
                _token_audit("register_denied", False, reason="bad_username", ip=ip)  # r32 F17
                return _JSONResp({"ok": False, "error": "用户名需 2-32 个字符"}, status_code=400)
            pwd = str(req.get("password") or "")
            if len(pwd) < 8:
                _token_audit("register_denied", False, reason="short_password", ip=ip)  # r32 F17
                return _JSONResp({"ok": False, "error": "密码至少 8 位"}, status_code=400)
            payload["password"] = pwd
            # r27 评审 P3（Cora）：先落 admin_name 再写密钥——名字落不上就中止注册
            # （注释"失败要出声"必须与实现一致：此前是保存失败+ok:True 静默，
            # 爸爸会被默认名挡在门外）。名字先落而密钥后写失败=注册窗口仍开，重试覆盖，无害。
            try:
                from settings_mgr import save_section as _ss
                _ss("general", {"admin_name": uname})
            except Exception as e:
                _token_audit("admin_name_save_failed", False, err=type(e).__name__, ip=ip)  # r32 F17 补 IP
                return _JSONResp({"ok": False, "error": "用户名保存失败，注册已中止——请重试"}, status_code=500)
        try:
            result = _guard_post("/set", payload, timeout=8.0)
        except urllib.error.HTTPError as e:
            # r32c F5（CB）：守卫原始 body 不再直透——解析后 error 过翻译层
            try:
                result = _rj.loads(e.read())
            except Exception:
                result = {"ok": False, "error": "被守卫拒绝"}
            if isinstance(result, dict) and result.get("error"):
                result = {"ok": False, "error": _human_error(result.get("error"))}
        except Exception as e:
            _token_audit("guard_error", False, err=type(e).__name__, ip=ip)  # r32 F17 补 IP
            return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)
        if not result.get("ok"):
            _token_audit("rotate_denied" if configured else "first_set_denied", False, ip=ip)
            # r32c F5（CB）：守卫英文/黑话过翻译层
            return _JSONResp({"ok": False, "error": _human_error(result.get("error") or "被守卫拒绝")}, status_code=403)
        val = payload["token"]
        clear_verify_cache()  # R10.11（Eve P3）：rotate/首设成功即清验证缓存，30s 撤销窗口压到 0
        _token_audit("first_set" if not configured else "rotate", True, ip=ip)
        if configured:
            # 轮换：新钥"只显一次"是 AdminTokenRow 展示流的依赖，保留响应体携带
            resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
        else:
            # r32 F8（Qoder P2）：注册路径不回吐明文钥——新 AuthPage 只判 ok、从不显示它，
            # 明文白走一趟响应体/代理/devtools。凭证=HttpOnly Cookie，浏览器内自动携带。
            resp = _JSONResp({"ok": True, "note": "注册成功，已登录（凭证保存在本机浏览器里，不上传）"})
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
            _token_audit("register_rate_limited", False, ip=ip)  # r32 F17
            return _JSONResp({"error": "注册尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
        uname = str(req.get("username") or "").strip()
        if not _valid_username(uname):
            _token_audit("register_denied", False, reason="bad_username", ip=ip)  # r32 F17
            return _JSONResp({"ok": False, "error": "用户名需 2-32 个字符"}, status_code=400)
        if len(str(req.get("password") or "")) < 8:
            _token_audit("register_denied", False, reason="short_password", ip=ip)  # r32 F17
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
            _token_audit("admin_name_save_failed", False, err=type(e).__name__, ip=ip)  # r32 F17 补 IP
            return _JSONResp({"ok": False, "error": "用户名保存失败，注册已中止——请重试"}, status_code=500)
        try:
            set_api_token(val)
        except Exception as e:
            # r32 F17（Qoder）：本地分支写钥零审计+裸 500——补审计与像样文案；窗口仍开可重试
            _token_audit("token_write_failed", False, err=type(e).__name__, ip=ip)
            return _JSONResp({"ok": False, "error": "密钥写入失败，注册已中止——请重试"}, status_code=500)
        _token_audit("first_set", True, ip=ip)
        # r32 F8：注册路径不回吐明文钥（同 guard 分支）
        resp = _JSONResp({"ok": True, "note": "注册成功，已登录（凭证保存在本机浏览器里，不上传）"})
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
# 注册/登录合一页（前端 AuthPage，r31 起；SetupWizard 已退役删除）：设密码+用户名；
# 忘记 Cookie → /auth/login 输密码 → 换回密钥并种 Cookie（密码持有者=管理员，语义等价找回）。
@router.post("/auth/set_password")
async def auth_set_password(req: dict = Body(...), request: Request = None):
    """设置管理员密码：浏览器路径证明=旧密码（r27 评审 P1-1 收紧，当前密钥不再代转）；
    宿主直连 guard 的救急通道（reset_password.cmd）另走物理信任锚，不经本端点。"""
    guard = M_GUARD_URL
    # R10.11（千问）：/auth/set_password 此前 office 侧无限频（guard 侧有 10/min 但每次拒绝仍落守卫审计行）——补同款分桶
    if not _boot_rate_ok("setpwd"):
        _token_audit("setpwd_rate_limited", False, ip=(request.client.host if request and request.client else "?"))  # r32c #17a
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
        # R10.8d：守卫的 403/429（密码太短/旧密码不符/限频）透传真实原因，不再谎报"不可达"；
        # r32 F9：英文/黑话先经 _human_error 翻译
        try:
            _body = e.read()
            import json as _ej
            _d = _ej.loads(_body)
            return _JSONResp({"ok": False, "error": _human_error(_d.get("error"))},
                             status_code=200 if e.code < 500 else e.code)
        except Exception:
            return _JSONResp({"ok": False, "error": "操作失败，请稍后再试"}, status_code=e.code)
    except Exception as _e:
        return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)


@router.post("/auth/login")
async def auth_login(req: dict = Body(...), request: Request = None):
    """密码找回登录：验证通过即种 Cookie 并返回密钥（仅此一次显示）。"""
    guard = M_GUARD_URL
    if not guard:
        return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)  # r32 F9：黑话原文"本地裸跑模式不支持（未配置守卫）"不进浏览器
    if not _boot_rate_ok("login"):
        _token_audit("login_rate_limited", False, ip=(request.client.host if request and request.client else "?"))  # r32c #17a
        return _JSONResp({"error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    # 09-17 OWUI 颗粒度对齐（爸爸令"登录名+登录密码"双要素）：登录名=注册时爸爸亲手
    # 所设（R10.408 起注册页必填），存 general.admin_name、设置页可改。
    # r32 F12（Qoder P2#11）：默认名改走 settings_schema 单源——"admin" 字面量第二真源拆除
    # （登录名比对是安全相关路径）。
    from settings_mgr import load_settings as _ls
    from settings_schema import default_of as _dof
    _want = str((_ls().get("general", {}) or {}).get("admin_name") or _dof("general.admin_name")).strip()
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
        # r32 F9：但守卫英文/黑话原文先经 _human_error 翻译——"missing guard key"
        # 这类绝不直穿登录页。
        try:
            _body = e.read()
            import json as _ej
            _d = _ej.loads(_body)
            return _JSONResp({"ok": False, "error": _human_error(_d.get("error"))},
                             status_code=200 if e.code < 500 else e.code)
        except Exception:
            return _JSONResp({"ok": False, "error": "操作失败，请稍后再试"}, status_code=e.code)
    except Exception as _e:
        return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)
    if not result.get("ok"):
        # 09-17 OWUI 同款泛化：密码错与登录名错同一句文案；r32 F9 再过一层翻译
        if str(result.get("error") or "") == "密码不正确":
            result = {"ok": False, "error": "登录名或密码不正确"}
        else:
            result = {"ok": False, "error": _human_error(result.get("error"))}
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
        _token_audit("clear_rate_limited", False, ip=(request.client.host if request and request.client else "?"))  # r32c #17a
        return _JSONResp({"error": "密钥管理操作过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    guard = M_GUARD_URL
    if guard:
        # R10.6：清除走守卫（guard 验当前密钥+清 DPAPI）。
        import json as _cj
        payload = {"token": _presented_token(request)}
        try:
            result = _guard_post("/clear", payload, timeout=8.0)
        except urllib.error.HTTPError as e:
            # R10.8c：HTTP 层拒绝透传守卫真实原因；r32c F5：error 过翻译层不再直透
            try:
                _d = _rj.loads(e.read())
                _d = {"ok": False, "error": _human_error(_d.get("error"))}
            except Exception:
                _d = {"ok": False, "error": "操作失败，请稍后再试"}
            return _JSONResp(_d, status_code=200 if e.code < 500 else e.code)
        except Exception as _e:
            print(f"[auth] clear 异常: {type(_e).__name__}: {_e}", flush=True)
            return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)
        if not result.get("ok"):
            return _JSONResp({"ok": False, "error": _human_error(result.get("error"))}, status_code=403)
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


# ── r31（09-26 爸爸令"看看 OWUI"）：登出端点——清 HttpOnly Cookie 即可，密钥不动 ──
@router.post("/auth/logout")
async def auth_logout(request: Request = None):
    """登出：只清浏览器 Cookie，管理员密钥和守卫不动（下次登录密码照用）。
    r32 F6：补限频桶+审计——此前全文件唯一没桶没账的端点（NOVA/Cora/CB 三路同锤）。
    r32 注记（Qoder P3 观察项）：SameSite=strict 挡不住 logout 型 CSRF（无需 Cookie 即生效），
    限频桶把"任意网页反复踢人下线"的成本抬起来；彻底堵法（自定义头）候多用户版一起做。"""
    if not _boot_rate_ok("logout"):
        _token_audit("logout_rate_limited", False, ip=(request.client.host if request and request.client else "?"))
        return _JSONResp({"ok": False, "error": "操作过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    ip = (request.client.host if request and request.client else "?")
    had_cookie = bool(_presented_token(request)) if _presented_token else False
    _token_audit("logout", True, ip=ip, had_cookie=had_cookie)
    resp = _JSONResp({"ok": True})
    resp.delete_cookie("m_admin_token", path="/")
    return resp


# ── 确认分档专用端点 ──
# 语义：plan<strict<auto_edit<full，四档自由切（放宽/收紧同权）。
# r29 曾设"放宽需管理员密码验证"——**r32 09-26 爸爸裁决撤除**："我们是个人平台，不是多用户
# 平台，管理员验证多此一举，等多用户平台版本再考虑"。guard /verify_password 端点保留备用，
# 顶栏/设置页四档直选无门槛。护栏残余=审计+回滚（谁改的、什么时候、改没改成，账本说话）
# + 限频桶 + _rev 防撞车。
# 通用 /settings/general 的 confirmLevel 写路已在 providers.py 关闭，HTTP 层无旁路
# （full 档宿主执行面=「米娅=知夏同等权限」定纲的 by-design 代价，r30 CB#4 在案）。
# 专审记录：confirm_level_change（旧→新+是否放宽+IP）落 **office 侧账本
# D:\m\secrets\token_audit.jsonl**（r30 CB#3 措辞更正——守卫自己的账本在
# D:\m\guard\token_audit.jsonl，两本同名，取证勿混）。
_TIER_RANK = {"plan": 0, "strict": 1, "auto_edit": 2, "full": 3}


@router.post("/settings/confirm-level")
async def api_set_confirm_level(req: dict = Body(...), request: Request = None):
    # r30 NOVA F5：_rev 防撞车（对照 providers.py 保存同款）——设置页保存与顶栏快切竞态时拒绝旧版请求
    expected_rev = req.pop("_rev", None)
    if expected_rev is not None:
        try:
            current_rev = settings_rev()  # r32 CB F13：单源微秒化
            if int(expected_rev) != current_rev:
                return _JSONResp({"ok": False, "conflict": True,
                                  "error": "设置已被后台修改（其他对话刚动过档位），请刷新页面后重试"}, status_code=409)
        except (ValueError, OSError):
            pass  # _rev 非数字或 stat 失败 → 不拦截（宽松路径；r32 起护栏=审计+回滚，密码门已撤）
    # r30 CB#5（glm-5.3 复测）：office 侧限频桶——此前 missing_password 路径不出守卫、
    # 不限频，持 token 者可全速刷审计账本（10MB×5 代旋转把既有证据挤出窗口）。
    if not _boot_rate_ok("confirm"):
        _token_audit("confirm_rate_limited", ok=False, ip=(request.client.host if request and request.client else "?"))
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
    # r32 09-26 爸爸裁决：放宽/收紧一律直切，密码门整段撤除（个人平台，等多用户版再考虑）。
    # 原块=missing_password 403 / guard /verify_password / 429 分译 / 503 fail-closed / bad_password 403。
    relaxed = _TIER_RANK[new] > _TIER_RANK[cur]
    save_section("general", {"confirmLevel": new})
    # r30 CB#2：审计失败=回滚——档位变更不许无痕生效（此前 _token_audit 吞异常，
    # secrets 卷不可写时档位变更不留痕；观测面静默=爸爸之恨 schtasks 同族）。
    # r32 F4（Qoder P1#4）：回滚成功/失败拆两条 return——旧版共用一条，回滚失败也谎报
    # "已回滚"，而档位实际停在放宽值；except 内审计补 strict=True 让失败必炸出来。
    try:
        _token_audit("confirm_level_change", ok=True, cur=cur, new=new, relaxed=relaxed, ip=ip, strict=True)
    except Exception as e:
        # r32c P1#3（Qoder）：旧版回滚分支里 strict 审计自己再抛=诚实文案永远到不了浏览器（裸 500）。
        # 拆清楚：回滚成败与审计成败是两回事——回滚尽力而为，审计尽力落账（不 strict），
        # 文案按"回滚真值"如实说。
        rolled_back = False
        try:
            save_section("general", {"confirmLevel": cur})
            rolled_back = True
        except Exception as _re:
            print(f"[confirm-level] 回滚也失败: {type(_re).__name__}: {_re}", flush=True)
        try:
            _token_audit("confirm_level_change_rollback", ok=rolled_back, reason=type(e).__name__, cur=new, new=cur, ip=ip)
        except Exception:
            pass  # 审计通道已坏，别再叠 500；真相已在服务日志
        if rolled_back:
            return _JSONResp({"ok": False, "error": "审计日志写入失败，档位已自动回滚，请排查 secrets 卷后重试"}, status_code=503)
        return _JSONResp({"ok": False,
                          "error": f"审计日志写入失败且自动回滚也失败——档位仍为 {new}，请立即人工到设置页收紧并排查 secrets 卷"},
                         status_code=503)
    return {"ok": True, "confirmLevel": new, "previous": cur}
