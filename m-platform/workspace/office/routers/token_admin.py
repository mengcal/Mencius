"""
office.routers.token_admin —— 激活码（bootstrap）+ /settings/token（status/首设/轮换/清除）+ /auth/*（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :16         urllib.error（区分"守卫拒绝（HTTPError 透传真实原因）"与"守卫不可达（503）"）
- :1159       import secrets as _secrets
- :1183-1199  _TOKEN_BOOTSTRAP + _bootstrap_read + _BOOT_LOCK
- :1220-1276  _BOOT_BUCKETS/_boot_rate_ok + _bootstrap_ensure + _bootstrap_drop + 启动即备好
- :1279-1281  _guard_url
- :1328-1420  GET /settings/token/status + POST /settings/token（首设/轮换）
- :1423-1501  POST /auth/set_password + POST /auth/login
- :1504-1550  DELETE /settings/token（清除）

注：_token_audit / _presented_token 下沉 core.py——前者被 misc 的 /approvals 复用，后者被 app.py 守卫复用。
原 :1161 顶层导入的 get_api_token 本模块未直接使用（_sdk_client 内有局部导入，留在 tasks.py），随原行保留导入以保真。
路由注册顺序：本模块必须在 providers 之前 include——POST /settings/token（实名路由）必须抢在
POST /settings/{section}（路径参数）之前，否则首设/轮换会被 {section} 吞掉（原源码序 :1333 早于 :1633）。
"""
import os
import threading
import time
import urllib.error  # 原 :16
import secrets as _secrets  # 原 :1159

from fastapi import APIRouter, Body, Request

from settings_mgr import clear_verify_cache, get_api_token, api_token_configured, set_api_token, token_ok as _token_ok  # 原 :1161

from ..core import _JSONResp, _RawResp, _ck, _presented_token, _secrets_dir, _token_audit

router = APIRouter()

# ── R10 修二（评审E P0-1）：首设密钥抢注 → 激活码走宿主 secrets 卷的带外文件 ──
# 旧首设只认 X-By: admin 明文头；沙箱经 host.docker.internal 回环摸得到 2024 发布口，
# 一条 curl 就能抢先设好密钥、把管理员反锁在门外（首设权=最高权，抢到就是永久）。
# 激活码=带外材料：只存在于宿主 secrets 卷（沙箱不可达），读得到文件的人才是管理员，
# 且一把激活码只兑现一次（首设成功即删）。
_TOKEN_BOOTSTRAP = _secrets_dir() / ".token_bootstrap"


def _bootstrap_read() -> str:
    """读激活码；文件缺失/不可读一律返回空串（调用方 fail-closed：空码谁也对不上）。"""
    try:
        return _TOKEN_BOOTSTRAP.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


_BOOT_LOCK = threading.Lock()  # R10.2（hy4 ②-5）：首设"读码→比对→写密钥→删码"全程持锁，封 TOCTOU 双开


_BOOT_BUCKETS: dict = {"bootstrap": [], "clear": [], "login": [], "rotate": []}  # R10.7b（hy4 P1-4）：按用途分桶


def _boot_rate_ok(purpose: str = "bootstrap") -> bool:
    """R10.2（hy4 ②-7）+R10.7b 分桶：首设/清除/登录/轮换各用各的窗口（60s≤10）——
    陌生登录流量不再把管理员自己的首设/清除一起 429。未配置态的 DELETE 也限频。"""
    hits = _BOOT_BUCKETS.setdefault(purpose, [])
    now = time.time()  # 原 :1229
    while hits and now - hits[0] > 60.0:
        hits.pop(0)
    if len(hits) >= 10:
        return False
    hits.append(now)
    return True


def _bootstrap_ensure() -> str:
    """确保激活码文件在：没有就现生一个（secrets.token_hex(16)，独占创建 + 0o600）。
    生成失败（secrets 卷不可写）返回空串→首设门闭合，宁可管理员手动放文件也不裸奔。
    R10.2（hy4 ②-4）：写码改 tmp+os.replace 原子落盘——O_EXCL 创建与 write 之间崩溃
    会留下半截/空文件常驻，旧版将永久闭合首设且无痕迹。"""
    cur = _bootstrap_read()
    if cur:
        return cur
    try:
        _TOKEN_BOOTSTRAP.parent.mkdir(parents=True, exist_ok=True)
        tmp = _TOKEN_BOOTSTRAP.with_name(_TOKEN_BOOTSTRAP.name + f".tmp{os.getpid()}")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_secrets.token_hex(16))
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(_TOKEN_BOOTSTRAP))  # 原子改名：读者只会看到"没有"或"完整"
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        print(f"[token] 已生成首设激活码文件（路径略，见 secrets 卷）", flush=True)
        _token_audit("bootstrap_ensure", True)
    except FileExistsError:
        pass  # 并发启动竞态：别人刚写好，直接读现成的
    except Exception as e:
        print(f"[token] 激活码文件生成失败（首设将不可用，需手动放文件）：{e}", flush=True)
    return _bootstrap_read()


def _bootstrap_drop() -> None:
    """首设成功即删激活码文件（一把码只兑现一次）。删不掉要出声，不留"以为删了"的哑状态。"""
    try:
        _TOKEN_BOOTSTRAP.unlink(missing_ok=True)
    except Exception as e:
        print(f"[token] 激活码文件删除失败（请手动清理 secrets 卷内 .token_bootstrap）：{e}", flush=True)


# 启动即备好：未配置密钥时先把激活码生成好，管理员随时能首设（不用重启）
if not api_token_configured():
    _bootstrap_ensure()


def _guard_url() -> str:
    """R10.6：m-guard 守卫服务地址（env 管理员配置；空=本地裸跑模式，走文件逻辑）。"""
    return (os.environ.get("M_GUARD_URL", "").strip().rstrip("/"))


@router.get("/settings/token/status")
async def api_token_status():
    return {"configured": api_token_configured()}


@router.post("/settings/token")
async def api_token_rotate(req: dict = Body(...), request: Request = None):
    """生成/轮换管理员密钥：已配置则必须带当前密钥（防被抢设/抢轮换锁死管理员）；
    未配置（首设）则必须带宿主 secrets 卷里的激活码（X-Bootstrap 头，R10 修二）。
    返回新值【仅此一次】，前端存 localStorage。
    R10.2（hy4 ②-5/②-6/②-7/②-8）：首设全程持锁封并发双开；比对走 _ck（非 ASCII 不炸 500）；
    首设尝试进 60s≤10 窗口（猜码轰炸无效化）；失败响应不再回显宿主绝对路径（信息泄露收口——
    带外码本来就只在 secrets 卷，路径对沙箱零价值，但按最小泄露原则不给）。"""
    configured = api_token_configured()
    ip = (request.client.host if request and request.client else "?")
    guard = _guard_url()
    if guard:
        # R10.6 守卫外置：密钥存取全走 m-guard（SYSTEM 常驻，明文不进本进程）。
        # 轮换证明=请求带来的当前钥匙；首设证明=X-Bootstrap 激活码（guard 验证+兑现）。
        import json as _rj
        import urllib.request as _ru
        current = _presented_token(request)
        payload = {"token": (req.get("token") or "").strip() or _secrets.token_hex(16)}
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
            if not _boot_rate_ok("bootstrap"):
                return _JSONResp({"error": "首设尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
            payload["bootstrap"] = str(request.headers.get("x-bootstrap") or "") if request else ""
            # R10.7b（hy4 P1-1 死锁修复）：注册向导单请求原子化——密码随首设一并落 guard
            if str(req.get("password") or ""):
                payload["password"] = str(req["password"])
        try:
            rq = _ru.Request(f"{guard}/set", data=_rj.dumps(payload).encode(),
                             headers={"Content-Type": "application/json",
                             "X-Guard-Key": os.environ.get("M_GUARD_KEY", "")}, method="POST")
            with _ru.urlopen(rq, timeout=8.0) as resp:
                result = _rj.loads(resp.read())
        except Exception as e:
            _token_audit("guard_error", False, err=type(e).__name__)
            return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)
        if not result.get("ok"):
            _token_audit("rotate_denied" if configured else "bootstrap_denied", False, ip=ip)
            return _JSONResp({"ok": False, "error": result.get("error", "被守卫拒绝")}, status_code=403)
        val = payload["token"]
        clear_verify_cache()  # R10.11（评审C P3）：rotate/首设成功即清验证缓存，30s 撤销窗口压到 0
        _token_audit("bootstrap_first_set" if not configured else "rotate", True, ip=ip)
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
        # R10 修二：首设不再认 X-By: admin 明文头（沙箱经宿主回环可伪造），改认带外激活码；
        # R10.2：常数时间+bytes 比对（_ck）+ 频控 + 持锁（读码→比对→写密钥→删码 原子段）。
        if not _boot_rate_ok("bootstrap"):
            return _JSONResp({"error": "首设尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
        with _BOOT_LOCK:
            expect = _bootstrap_read()
            given = str(request.headers.get("x-bootstrap") or "") if request else ""
            if not expect or not _ck(expect, given):
                _token_audit("bootstrap_denied", False, ip=ip)
                return _JSONResp(
                    {"ok": False,
                     "error": "首次设置管理员密钥需激活码：宿主电脑 D:\\m\\guard\\.token_bootstrap "
                              "文件里的全部内容（注册向导可直接粘贴）。该文件夹已锁管理员——"
                              "拿得出激活码的才是管理员（注册页已提供粘贴输入框）"},
                    status_code=403)
            val = (req.get("token") or "").strip() or _secrets.token_hex(16)
            set_api_token(val)
            _bootstrap_drop()  # 一把激活码只兑现一次（与写密钥同持锁区，兑现后不留第二把）
        _token_audit("bootstrap_first_set", True, ip=ip)
        resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
        resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                        max_age=30 * 24 * 3600, path="/")  # R10.5 XSS L2：JS 读不到的浏览器凭证
        return resp
    val = (req.get("token") or "").strip() or _secrets.token_hex(16)
    set_api_token(val)
    clear_verify_cache()  # R10.11（评审C P3）：本地模式轮换即时生效
    _token_audit("rotate", True, ip=ip)
    resp = _JSONResp({"ok": True, "token": val, "note": "只显这一次，存好；此后改设置/服务商/批准都要带上它"})
    resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")
    return resp


# ── R10.7（管理员："发布到 GitHub，没基础的用户怎么取得管理员权限"）：密码注册+找回 ──
# 注册向导（前端 SetupWizard，未配置时全屏展示）：激活码+设密码；
# 忘记 Cookie → /auth/login 输密码 → 换回密钥并种 Cookie（密码持有者=管理员，语义等价找回）。
@router.post("/auth/set_password")
async def auth_set_password(req: dict = Body(...), request: Request = None):
    """设置管理员密码：证明=当前密钥（Bearer/Cookie）或激活码（首设流程）。"""
    guard = _guard_url()
    # R10.11（评审E）：/auth/set_password 此前 office 侧无限频（guard 侧有 10/min 但每次拒绝仍落守卫审计行）——补同款分桶
    if not _boot_rate_ok("setpwd"):
        return _JSONResp({"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    if not guard:
        return _JSONResp({"ok": False, "error": "本地裸跑模式不支持（未配置守卫）"}, status_code=503)
    import json as _pj
    import urllib.request as _pu
    payload = {"password": str(req.get("password") or "")}
    current = _presented_token(request)
    if current:
        payload["current"] = current
    boot = str(req.get("bootstrap") or "")
    if boot:
        payload["bootstrap"] = boot
    old_pwd = str(req.get("old_password") or "")
    if old_pwd:
        payload["old_password"] = old_pwd  # R10.8d：改找回密码必须验旧密码
    try:
        rq = _pu.Request(f"{guard}/set_password", data=_pj.dumps(payload).encode(),
                         headers={"Content-Type": "application/json",
                             "X-Guard-Key": os.environ.get("M_GUARD_KEY", "")}, method="POST")
        with _pu.urlopen(rq, timeout=8.0) as resp:
            result = _pj.loads(resp.read())
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
    guard = _guard_url()
    if not guard:
        return _JSONResp({"ok": False, "error": "本地裸跑模式不支持（未配置守卫）"}, status_code=503)
    if not _boot_rate_ok("login"):
        return _JSONResp({"error": "尝试过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    import json as _lj
    import urllib.error as _lue  # R10.8c：区分"守卫拒绝（HTTPError 透传真实原因）"与"守卫不可达（503）"
    import urllib.request as _lu
    try:
        rq = _lu.Request(f"{guard}/login", data=_lj.dumps({"password": str(req.get("password") or "")}).encode(),
                         headers={"Content-Type": "application/json",
                             "X-Guard-Key": os.environ.get("M_GUARD_KEY", "")}, method="POST")
        with _lu.urlopen(rq, timeout=8.0) as resp:
            result = _lj.loads(resp.read())
    except urllib.error.HTTPError as e:
        # R10.8d：login 的 403/429（密码不符/锁定/未设密码）透传真实原因。
        # R10.11（评审C）：改 _RawResp 原样透传——旧写法把守卫 JSON 塞进 {"error": "<json字符串>"} 双层
        # 包装，前端拿到一坨转义串（对照同文件 set_password 的正确写法）。
        try:
            _body = e.read()
        except Exception:
            _body = b'{"ok": false}'
        return _RawResp(_body, status_code=e.code, media_type="application/json")
    except Exception as _e:
        return _JSONResp({"ok": False, "error": "守卫服务不可达（fail-closed）"}, status_code=503)
    if not result.get("ok"):
        return _JSONResp(result, status_code=200)
    val = result["token"]
    _token_audit("login_password", True, ip=(request.client.host if request and request.client else "?"))
    # R10.8d（管理员被挤掉线 N 次的教训）：office 层不做第二次轮换——rotate 发生在 guard /login 内
    # （重签发新密钥，评审E P0-1：找回不回吐旧明文），本端点只把【新密钥】种进 HttpOnly Cookie，
    # 明文不经响应体。对单浏览器用户无感（立即拿到新 Cookie）；旧凭证同时作废。
    # 测试密码请用 guard /verify_password（只验不签发，绝不触发本链路）。
    resp = _JSONResp({"ok": True, "note": "登录成功（Cookie 已种入）"})
    resp.set_cookie("m_admin_token", val, httponly=True, samesite="strict",
                    max_age=30 * 24 * 3600, path="/")
    return resp


@router.delete("/settings/token")
async def api_token_clear(request: Request = None):
    """清除管理员密钥（回到未配置=放行）。需当前密钥。用于管理员彻底重置。
    R10 修二：清除后立刻重建激活码文件——下次首设仍要激活码，否则"清除"=把首设门重新敞给沙箱。
    R10.2（hy4 ②-7）：未配置态的 DELETE 不再无限免凭证调用（反复触发建码/IO）——进首设同一窗口。"""
    if not _boot_rate_ok("clear"):
        return _JSONResp({"error": "密钥管理操作过于频繁（60 秒内最多 10 次），稍后再试"}, status_code=429)
    guard = _guard_url()
    if guard:
        # R10.6：清除走守卫（guard 验当前密钥+清 DPAPI+重建激活码）。
        # R10.7b（hy4 P1-2）：未配置态的清除要激活码证明——X-Bootstrap 透传给 guard。
        import json as _cj
        import urllib.request as _cu
        payload = {"token": _presented_token(request)}
        if not api_token_configured():
            payload["bootstrap"] = str(request.headers.get("x-bootstrap") or "") if request else ""
        try:
            rq = _cu.Request(f"{guard}/clear", data=_cj.dumps(payload).encode(),
                             headers={"Content-Type": "application/json",
                             "X-Guard-Key": os.environ.get("M_GUARD_KEY", "")}, method="POST")
            with _cu.urlopen(rq, timeout=8.0) as resp:
                result = _cj.loads(resp.read())
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
        clear_verify_cache()  # R10.11（评审C P3）：清除密钥=撤销即时生效，不等 30s TTL
        resp = _JSONResp({"ok": True, "cleared": True})
        resp.delete_cookie("m_admin_token", path="/")
        return resp
    if api_token_configured() and not _token_ok(_presented_token(request)):
        return {"ok": False, "error": "清除需当前密钥"}
    ip = (request.client.host if request and request.client else "?")
    set_api_token("")
    clear_verify_cache()  # R10.11（评审C P3）：本地模式清除同样即时撤销
    _bootstrap_ensure()
    _token_audit("token_clear", True, ip=ip)
    resp = _JSONResp({"ok": True, "cleared": True})
    resp.delete_cookie("m_admin_token", path="/")  # R10.5：清除=浏览器 Cookie 一并作废
    return resp
