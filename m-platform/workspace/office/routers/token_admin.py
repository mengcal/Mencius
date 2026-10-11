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
import secrets as _secrets  # 原 :1159

from fastapi import APIRouter, Body, Request

from settings_mgr import (clear_verify_cache, get_api_token, api_token_configured, set_api_token,
                          token_ok as _token_ok, get_plain_key, secret_set,
                          load_settings, save_section, settings_rev, BASE)  # 原 :1161；10-11 守卫族退役：M_GUARD_URL/_guard_post 整族移除（eng-log R10.661），本地 .settings_secrets 单源

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


# 10-11 守卫退役：_GUARD_ERROR_ZH/_human_error 翻译层随守卫分支整族移除
# （本地路径的错误文本本来就是中文人话直返）。


@router.get("/settings/token/status")
async def api_token_status():
    # 10-11 守卫退役：三态收敛为本地单态——configured 直接读 .settings_secrets。
    return {"configured": api_token_configured(), "guard": False, "unreachable": False}


@router.post("/settings/token")
async def api_token_rotate(req: dict = Body(...), request: Request = None):
    """生成/轮换管理员密钥：已配置则必须带当前密钥（防被抢轮换锁死爸爸）；
    未配置（首设=注册）：R10.408 起无激活码——直接提交 username+password，
    谁先注册谁是主人；用户名落 general.admin_name（登录双要素的"名"由此而来）。
    返回新值【仅此一次】，前端种 HttpOnly Cookie。
    10-11：guard 分支整族退役（守卫服务已删），仅余本地 .settings_secrets 单源路径。"""
    configured = api_token_configured()
    ip = (request.client.host if request and request.client else "?")
    if configured:
        if not _token_ok(_presented_token(request)):
            _token_audit("rotate_denied", False, ip=ip)
            return {"ok": False, "error": "轮换管理员密钥需当前密钥"}
        val = (req.get("token") or "").strip() or _secrets.token_hex(16)
        set_api_token(val)
        clear_verify_cache()  # R10.11（Eve P3）：本地模式轮换即时生效
        _token_audit("rotate", True, ip=ip)
        # 轮换：新钥"只显一次"是 AdminTokenRow 展示流的依赖，保留响应体携带
        resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
        resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                        max_age=30 * 24 * 3600, path="/")
        return resp
    # 首设=注册窗口（用户名+密码）
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
    # r30 Cora#6：先落名、落不上即中止（此时密钥未写、注册窗口仍开，重试无害）。
    try:
        save_section("general", {"admin_name": uname})
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
    # r32 F8：注册路径不回吐明文钥
    resp = _JSONResp({"ok": True, "note": "注册成功，已登录（凭证保存在本机浏览器里，不上传）"})
    resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")  # R10.5 XSS L2：JS 读不到的浏览器凭证
    return resp


# ── R10.7（爸爸："发布到 GitHub，没基础的用户怎么取得管理员权限"）：密码注册+找回 ──
# 注册/登录合一页（前端 AuthPage，r31 起；SetupWizard 已退役删除）：设密码+用户名；
# 忘记 Cookie → /auth/login 输密码 → 换回密钥并种 Cookie（密码持有者=管理员，语义等价找回）。
@router.post("/auth/set_password")
async def auth_set_password(req: dict = Body(...), request: Request = None):
    """设置管理员密码（10-11 本地化，守卫退役前此端点恒 503=改密码功能死了）：
    浏览器路径证明=旧密码（r27 评审 P1-1，防持 Cookie 的 XSS 无旧密码换锁）；
    新密码 sha256("mencia-salt:"+pw) 落 .settings_secrets 的 general.password_hash，
    与 /auth/login 同款哈希——登录/改密互证。"""
    import hashlib as _hl
    if not _boot_rate_ok("setpwd"):
        _token_audit("setpwd_rate_limited", False, ip=(request.client.host if request and request.client else "?"))  # r32c #17a
        return _JSONResp({"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    _want_hash = get_plain_key("general.password_hash").strip()
    _old = str(req.get("old_password") or "")
    if _want_hash:
        # 已设密码：必须验旧密码（R10.8d：改找回密码必须验旧密码）
        if not _old or not _hl.compare_digest(
                _want_hash, _hl.sha256(("mencia-salt:" + _old).encode()).hexdigest()):
            _token_audit("setpwd_denied", False, reason="old_password_mismatch",
                         ip=(request.client.host if request and request.client else "?"))
            return _JSONResp({"ok": False, "error": "旧密码不正确"}, status_code=403)
    _new = str(req.get("password") or "")
    if len(_new) < 8:
        _token_audit("setpwd_denied", False, reason="short_password",
                     ip=(request.client.host if request and request.client else "?"))
        return _JSONResp({"ok": False, "error": "密码至少 8 位"}, status_code=400)
    secret_set("general.password_hash",
               _hl.sha256(("mencia-salt:" + _new).encode()).hexdigest())
    _token_audit("set_password", True, had_old=bool(_want_hash),
                 ip=(request.client.host if request and request.client else "?"))
    return {"ok": True, "note": "密码已设置/更新（下次登录用新密码）"}


@router.post("/auth/login")
async def auth_login(req: dict = Body(...), request: Request = None):
    """密码找回登录：验证通过即种 Cookie 并返回密钥（仅此一次显示）。
    10-03 守卫退役后本地化：密码 hash 存 .settings_secrets 的 general.password_hash
    （sha256("mencia-salt:"+密码)），token=general.apiToken——不再依赖 m-guard。
    10-11：guard 分支整族移除，本地路径即唯一路径。"""
    if not _boot_rate_ok("login"):
        _token_audit("login_rate_limited", False, ip=(request.client.host if request and request.client else "?"))
        return _JSONResp({"error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    from settings_schema import default_of as _dof
    import hashlib as _hl, hmac as _hm
    _want_name = str((load_settings().get("general", {}) or {}).get("admin_name") or _dof("general.admin_name")).strip()
    _want_hash = get_plain_key("general.password_hash").strip()
    _got_name = str(req.get("username") or "").strip()
    _got_pw = str(req.get("password") or "")
    _name_ok = _got_name == _want_name
    _pw_ok = bool(_want_hash) and _hm.compare_digest(
        _want_hash, _hl.sha256(("mencia-salt:" + _got_pw).encode()).hexdigest())
    if not (_name_ok and _pw_ok):
        _token_audit("login_local_fail", False, ip=(request.client.host if request and request.client else "?"))
        return _JSONResp({"ok": False, "error": "登录名或密码不正确"}, status_code=200)
    _token = get_api_token().strip()
    if not _token:
        return _JSONResp({"ok": False, "error": "服务暂时不可用，请稍后再试"}, status_code=503)
    _token_audit("login_local", True, ip=(request.client.host if request and request.client else "?"))
    resp = _JSONResp({"ok": True, "note": "登录成功（Cookie 已种入）"})
    resp.set_cookie("m_admin_token", _token, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")
    return resp


@router.delete("/settings/token")
async def api_token_clear(request: Request = None):
    """清除管理员密钥（回到未配置=注册窗口重新开放）。需当前密钥。用于爸爸彻底重置。
    R10.408：清除后不再重建激活码——注册流程已反转为"谁先注册谁是主人"。
    R10.2（hy4 ②-7）：未配置态的 DELETE 限频（防洪水 IO）。
    10-11：guard 分支整族移除，仅余本地路径。"""
    if not _boot_rate_ok("clear"):
        _token_audit("clear_rate_limited", False, ip=(request.client.host if request and request.client else "?"))  # r32c #17a
        return _JSONResp({"error": "密钥管理操作过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
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
    had_cookie = bool(_presented_token(request))  # r35（Qoder P3-4）：去掉对函数对象的恒真 if 判断
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
