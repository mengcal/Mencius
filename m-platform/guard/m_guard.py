"""m_guard.py — M平台守卫服务（R10.6，管理员拍板"一次做成 外置式守卫外置"）。

参照两条成熟模式（2026-09-06 调研）：
- ssh-agent：密钥常驻守卫进程内存/本地加密存储，**只提供"验证通过/不通过"，永不外发明文**；
- DPAPI（Windows 数据保护 API，user scope）：以运行账户（SYSTEM）加密落盘——其他 Windows 账户物理解不开。

威胁模型（助手终态=专属标准账户+宿主全权）：
- 她可以打到 127.0.0.1:9101（问验证），但拿不到明文、改不了判定；
- 她读不了 DPAPI(SYSTEM) 加密的 token.bin、停不掉 SYSTEM 任务、改不了本目录（icacls 已锁 SYSTEM+Administrators+主机登录用户）；
- 她要越界=UAC 弹管理员密码。

端点：
- GET  /status            → {"configured": bool}（无敏感）
- POST /verify {token}    → {"ok": bool}（常数时间；限频；审计；永不回明文）
- POST /set    {token, bootstrap?} → 设置密钥：未配置态须 bootstrap 激活码正确（guard 自己生成/验证/兑现激活码）
- POST /clear  {token}    → 清除（须当前密钥）；清后重建激活码
- GET  /bootstrap/status  → {"exists": bool}
审计：每动作落 guard 目录 token_audit.jsonl + stdout（双通道）。
"""
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GUARD_DIR = Path(__file__).resolve().parent
TOKEN_BLOB = GUARD_DIR / "token.bin"
PASSWORD_BLOB = GUARD_DIR / "password.bin"
AUDIT_LOG = GUARD_DIR / "token_audit.jsonl"
BOOTSTRAP_FILE = Path(os.environ.get("M_GUARD_BOOTSTRAP", str(GUARD_DIR / ".token_bootstrap")))
HOSTCOPY = Path(os.environ.get("M_GUARD_HOSTCOPY", str(GUARD_DIR / "hostcopy.token")))
_PORT = int(os.environ.get("M_GUARD_PORT", "9101"))


def _load_dotenv_mini() -> None:
    r"""R10.8c（致命修复）：SYSTEM 计划任务启动的进程环境里没有用户 .env——
    M_GUARD_KEY 读成空串 → 所有带钥匙请求被 403（管理员注册 503 真凶）。
    启动时从 D:\m\.env 提取 M_GUARD_* 变量（进程已有环境变量优先）。"""
    env_file = Path(os.environ.get("M_GUARD_ENV_FILE", r"D:\m\.env"))
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith("M_GUARD_") and k not in os.environ:
                os.environ[k] = v.strip()
    except OSError:
        pass


_load_dotenv_mini()

_LOGIN_HITS: list = []  # /login 严格限频（10/min）：防密码爆破
_LOGIN_FAILS = {"n": 0, "until": 0.0}  # R10.8（评审C P2-2）：连续失败≥5 → 锁 300s
GUARD_KEY = os.environ.get("M_GUARD_KEY", "")  # R10.8（评审B 🔴A/评审C P1-1）：通信钥匙——
# 宿主回环被 host.docker.internal 转发成"所有容器可达"，且转发后源 IP 一律 127.0.0.1
# （实测 token_audit 证实）——网络位置不再构成身份，/verify /set /set_password /clear
# 必须带 X-Guard-Key（workplatform env 独有，沙箱 env 没有）；R10.11 起含 /login——
# 它是唯一能签发新管理员密钥的端点且 office 调用本就带钥匙；/status 保持无钥匙可达（信息量极低）。

_HITS: list = []  # verify 限频（300/min）
_SET_HITS: list = []      # R10.7b（hy4 P1-3）：/set 与 /set_password 独立限频桶（10/min）
# R10.8（hy4 测试套抓到死锁）：_write_token 持锁路径里 hostcopy 失败会调 _audit →
# _audit 也用同一把锁 → threading.Lock 不可重入=自锁死。换 RLock（重入安全）。
_LOCK = threading.RLock()


# ── DPAPI（user scope）：密钥落盘加密，只有运行 guard 的账户（SYSTEM）能解 ──
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_protect(data: bytes) -> bytes:
    bin_ = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(bin_), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    bin_ = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(bin_), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _read_token() -> str:
    try:
        return _dpapi_unprotect(TOKEN_BLOB.read_bytes()).decode("utf-8").strip()
    except Exception:
        return ""


# ── R10.7（管理员："发布后普通用户怎么取得管理员权限"）：密码找回通道 ──
# 注册（首设）时设管理员密码 → PBKDF2(200k) 哈希后 DPAPI 加密落 password.bin；
# 忘记 Cookie 时用密码找回：/login 验证通过即发回当前密钥明文（密码持有者=管理员，语义等价找回）。
def _hash_password(pwd: str) -> str:
    import hashlib as _hl
    import secrets as _s
    salt = _s.token_bytes(16)
    dk = _hl.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + dk.hex()


def _check_password(pwd: str, stored: str) -> bool:
    import hashlib as _hl
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        dk = _hl.pbkdf2_hmac("sha256", pwd.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
        return _ck(dk.hex(), dk_hex)
    except Exception:
        return False


def _read_password_hash() -> str:
    try:
        return _dpapi_unprotect(PASSWORD_BLOB.read_bytes()).decode("utf-8").strip()
    except Exception:
        return ""


def _write_password_hash(h: str) -> None:
    with _LOCK:
        tmp = PASSWORD_BLOB.with_name(PASSWORD_BLOB.name + ".tmp")
        tmp.write_bytes(_dpapi_protect(h.encode("utf-8")))
        os.replace(str(tmp), str(PASSWORD_BLOB))


def _login_rate_ok() -> bool:
    now = time.time()
    with _LOCK:
        while _LOGIN_HITS and now - _LOGIN_HITS[0] > 60.0:
            _LOGIN_HITS.pop(0)
        if len(_LOGIN_HITS) >= 10:
            return False
        _LOGIN_HITS.append(now)
    return True


def _set_rate_ok() -> bool:
    """R10.7b（hy4 P1-3）：/set 与 /set_password 限频（10/min）——
    无凭证的 DPAPI 解封装+文件读也是 CPU/IO 面，洪水同样要钳。"""
    now = time.time()
    with _LOCK:
        while _SET_HITS and now - _SET_HITS[0] > 60.0:
            _SET_HITS.pop(0)
        if len(_SET_HITS) >= 10:
            return False
        _SET_HITS.append(now)
    return True


def _write_token(val: str) -> None:
    # R10.6b（hy4 F10）：tmp+replace 原子写+_LOCK——半写崩溃曾可致 token.bin 损坏 →
    # _read_token()="" → 连带 F2 fail-open。并发下也保证"要么旧值要么新值"。
    with _LOCK:
        tmp = TOKEN_BLOB.with_name(TOKEN_BLOB.name + ".tmp")
        tmp.write_bytes(_dpapi_protect(val.encode("utf-8")))
        os.replace(str(tmp), str(TOKEN_BLOB))
    _write_hostcopy(val)


def _write_hostcopy(val: str) -> None:
    """宿主测试副本（m-gates.sh 等宿主脚本用）：DPAPI 解不开时唯一明文落点。
    迁移脚本会 icacls 收紧为 Administrators+SYSTEM——未来助手标准账户读不到。
    容器内进程与沙箱永远摸不到（宿主文件）。写失败只审计不阻断。"""
    try:
        HOSTCOPY.write_text(val, encoding="utf-8")
        # R10.6b（hy4 F13 缓解）：明文副本 ACL 收紧到 SYSTEM+Administrators+当前账户——
        # 未来助手标准账户读不到；迁移后如需彻底消除明文落盘，改由 m-gates 向管理员要 Cookie 值。
        try:
            import subprocess as _sp
            user = os.environ.get("USERNAME", "")
            grants = ["SYSTEM:F", "Administrators:F"] + ([f"{user}:F"] if user else [])
            _r = _sp.run(["icacls", str(HOSTCOPY), "/inheritance:r", "/grant:r", *grants],
                         capture_output=True, timeout=10)
            if _r.returncode != 0:  # R10.11（评审E）：icacls 失败不再静默——明文副本的 ACL 是唯一宿主侧防护
                _audit("hostcopy_acl_failed", rc=_r.returncode)
        except Exception as e:
            _audit("hostcopy_acl_failed", err=type(e).__name__)
    except Exception as e:
        _audit("hostcopy_failed", err=type(e).__name__)


def _del_token() -> None:
    try:
        TOKEN_BLOB.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        HOSTCOPY.unlink(missing_ok=True)
    except OSError:
        pass


def _del_password() -> None:
    """R10.7：清密钥时密码一并作废（重置=回到全新状态，注册向导会重新设密码）。"""
    try:
        PASSWORD_BLOB.unlink(missing_ok=True)
    except OSError:
        pass


_AUDIT_ROTATE_BYTES = 10 * 1024 * 1024  # R10.11（评审E P1-3）：守卫账本 10MB 三代轮转——与 office/core._rotate_log 同款
                                        # 此前纯 append 无上限（/login 无钥匙 10/min 可日增 1.4MB），磁盘写满会打断 _write_token 原子写


def _audit_rotate() -> None:
    try:
        if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > _AUDIT_ROTATE_BYTES:
            for i in (3, 2, 1):
                nxt = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{i + 1}")
                cur = AUDIT_LOG.with_name(f"{AUDIT_LOG.name}.{i}")
                if cur.exists():
                    nxt.unlink(missing_ok=True)
                    cur.replace(nxt)
            AUDIT_LOG.replace(AUDIT_LOG.with_name(AUDIT_LOG.name + ".1"))
    except OSError:
        pass


def _audit(action: str, **extra) -> None:
    import datetime as _dt
    rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "action": action}
    rec.update({k: str(v)[:80] for k, v in extra.items()})
    line = json.dumps(rec, ensure_ascii=False)
    print(f"[m-guard] {line}", flush=True)
    try:
        with _LOCK:
            _audit_rotate()
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass


def _ck(a: str, b: str) -> bool:
    import hmac as _h
    try:
        return _h.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))
    except Exception:
        return False


def _bootstrap_read() -> str:
    try:
        return BOOTSTRAP_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _bootstrap_ensure() -> str:
    cur = _bootstrap_read()
    if cur:
        return cur
    import secrets as _s
    try:
        BOOTSTRAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOOTSTRAP_FILE.write_text(_s.token_hex(16), encoding="utf-8")
        # R10.6b（hy4 F17）：旧版用 chmod(0o600)——Windows 上无效语义。改用 icacls 收紧 ACL：
        # 只留 SYSTEM、Administrators 与【当前运行账户】（非提权令牌不在 Administrators 组里，
        # 不加这一条守卫自己都读不回激活码——hy4 测试套当场抓到）。
        try:
            import subprocess as _sp
            user = os.environ.get("USERNAME", "")
            grants = ["SYSTEM:F", "Administrators:F"] + ([f"{user}:F"] if user else [])
            _sp.run(["icacls", str(BOOTSTRAP_FILE), "/inheritance:r", "/grant:r", *grants],
                    capture_output=True, timeout=10)
        except Exception as e:
            _audit("bootstrap_acl_failed", err=type(e).__name__)  # R10.11（评审E）：注释说"只审计"就真审计——此前 except pass 静默
        _audit("bootstrap_ensure")
    except Exception as e:
        _audit("bootstrap_failed", err=type(e).__name__)
    return _bootstrap_read()


def _bootstrap_drop() -> None:
    try:
        BOOTSTRAP_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _rate_ok() -> bool:
    now = time.time()
    with _LOCK:
        while _HITS and now - _HITS[0] > 60.0:
            _HITS.pop(0)
        if len(_HITS) >= 300:
            return False
        _HITS.append(now)
    return True


class Handler(BaseHTTPRequestHandler):
    timeout = 30  # R10.6b（hy4 F6）：慢速连接不再占死线程

    def log_message(self, *a):
        pass

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send(200, {"configured": bool(_read_token()), "service": "m-guard"})
        elif self.path == "/bootstrap/status":
            self._send(200, {"exists": bool(_bootstrap_read())})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        # R10.6b（hy4 F7）：顶层兜底——任何未捕获异常返回 400 并落审计，不再崩线程/无痕。
        try:
            self._do_post()
        except Exception as e:
            _audit("unhandled_error", err=type(e).__name__, ip=self._client_ip())
            try:
                self._send(400, {"error": "bad request"})
            except OSError:
                pass

    def _client_ip(self):
        return self.client_address[0] if self.client_address else "?"

    def _key_ok(self):
        """R10.8：/verify /set /set_password /clear 必须带 X-Guard-Key（平台进程 env 独有）。
        无/错=403（不占任何桶）——沙箱挤兑链整体断。"""
        return bool(GUARD_KEY) and _ck(str(self.headers.get("X-Guard-Key") or ""), GUARD_KEY)

    def _do_post(self):
        try:
            ln = int(self.headers.get("Content-Length", "0"))
        except Exception:
            self._send(400, {"error": "bad json"})
            return
        # R10.6b（hy4 F6）：体积闸——声明超过 64KB 直接拒，不再无上限攒内存
        if ln > 65536:
            _audit("body_too_large", ln=ln, ip=self._client_ip())
            self._send(413, {"error": "body too large"})
            return
        try:
            raw = self.rfile.read(ln) if ln else b""
            if ln <= 0:  # R10.6b（hy4 F9）：空 body 不再当 {}——无证明的请求直接 400
                raise ValueError("empty body")
            req = json.loads(raw)
            if not isinstance(req, dict):  # R10.6b（hy4 F7）：顶层非 dict 一律 400
                raise ValueError("not an object")
        except Exception:
            _audit("bad_json", ip=self._client_ip())
            self._send(400, {"error": "bad request"})
            return
        ip = self._client_ip()
        if self.path == "/verify":
            if not self._key_ok():
                _audit("verify_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            if not _rate_ok():
                _audit("verify_rate_limited", ip=ip)
                self._send(429, {"ok": False, "error": "rate limited"})
                return
            cur = _read_token()
            # R10.6b（hy4 F2 P0 fail-open）：未配置/密钥缺失时 _read_token()==""，
            # 与提交的空令牌 _ck 相等会返回 ok=True——这里先判空 fail-closed。
            ok = bool(cur) and _ck(cur, str(req.get("token") or ""))
            _audit("verify", ok=ok, ip=ip)
            self._send(200, {"ok": ok})  # 永不返回明文
            return
        if self.path == "/set":
            if not self._key_ok():
                _audit("set_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            # R10.7b（hy4 P1-1 死锁修复）：首设原子化——token+密码（可选）+删激活码
            # 在同一持锁段一次完成，不存在"码已废、密码未落"的中间态。
            val = str(req.get("token") or "").strip()
            boot = str(req.get("bootstrap") or "").strip()
            pwd = str(req.get("password") or "")
            if not val:
                self._send(400, {"ok": False, "error": "token required"})
                return
            if not _set_rate_ok():
                _audit("set_rate_limited", ip=ip)
                self._send(429, {"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次）"})
                return
            with _LOCK:
                if _read_token():
                    # 已配置：须当前密钥作证明（轮换）
                    if not _ck(str(req.get("current") or ""), _read_token()):
                        _audit("set_denied", reason="bad current", ip=ip)
                        self._send(403, {"ok": False, "error": "轮换需当前密钥"})
                        return
                    if pwd and len(pwd) < 8:
                        # R10.8：校验必须先于写入——密码太短被拒时密钥不能已经被轮换（半完成状态）
                        self._send(400, {"ok": False, "error": "密码至少 8 位"})
                        return
                    _write_token(val)
                    if pwd:
                        _write_password_hash(_hash_password(pwd))
                    _audit("rotate", ip=ip, with_password=bool(pwd))
                    self._send(200, {"ok": True})
                    return
                # 未配置（首设）：须激活码——带外文件只在宿主，谁拿得出谁是管理员
                expect = _bootstrap_read()
                if not expect or not _ck(expect, boot):
                    _audit("bootstrap_denied", ip=ip)
                    self._send(403, {"ok": False,
                                     "error": "首设需激活码（部署目录 guard 文件夹的 .token_bootstrap 文件内容，注册页可粘贴）"})
                    return
                if pwd and len(pwd) < 8:
                    self._send(400, {"ok": False, "error": "密码至少 8 位"})
                    return
                _write_token(val)
                if pwd:
                    _write_password_hash(_hash_password(pwd))
                _bootstrap_drop()  # 兑现即删——与写 token/密码同持锁段（P1-1：无中间态）
            _audit("bootstrap_first_set", ip=ip, with_password=bool(pwd))
            self._send(200, {"ok": True})
            return
        if self.path == "/set_password":
            if not self._key_ok():
                _audit("set_password_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            # R10.7：注册后补设/更换密码。证明=当前密钥（已配置）。
            if not _set_rate_ok():
                _audit("set_password_rate_limited", ip=ip)
                self._send(429, {"ok": False, "error": "尝试过于频繁"})
                return
            pwd = str(req.get("password") or "")
            if len(pwd) < 8:
                self._send(400, {"ok": False, "error": "密码至少 8 位"})
                return
            cur = _read_token()
            stored = _read_password_hash()
            # R10.8d（管理员："怎么修改密码"）：修改找回密码的证明路径——
            #   ① 旧密码验证通过（知道旧密码=有权改，最用户友好）
            #   ② 当前密钥证明（CLI/API 场景）
            # 两者任一通过即可。防持久化攻击：旧密码验证仍然必须。
            old_pwd = str(req.get("old_password") or "")
            proved = False
            if stored and old_pwd and _check_password(old_pwd, stored):
                proved = True  # 旧密码验证
            elif cur and _ck(str(req.get("current") or ""), cur):
                proved = True  # 当前密钥证明（CLI/API 场景）
            if not proved:
                reason = "旧密码不正确" if (stored and old_pwd) else "需当前密钥或旧密码作为证明"
                _audit("set_password_denied", reason=reason, ip=ip)
                self._send(403, {"ok": False, "error": reason})
                return
            _write_password_hash(_hash_password(pwd))
            _audit("password_set", ip=ip)
            self._send(200, {"ok": True})
            return
        if self.path == "/login":
            # R10.7：密码找回——验证通过即 rotate 重签发新密钥（评审E P0-1：找回不回吐旧明文）。
            # R10.11（评审E P0-1 收口）：补 X-Guard-Key 门——本端点是唯一能签发新管理员密钥的
            # 入口，此前却是钥匙门最弱的（只有密码一道）。合法调用方 office /auth/login 本就
            # 带钥匙（token_admin.py:266），补门零破坏；无钥匙的 /login 只服务于没有钥匙的
            # 攻击者（沙箱经 host.docker.internal 可达 9101，5 败锁可被无限触发=锁死找回通道）。
            if not self._key_ok():
                _audit("login_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            # 严格限频 10/min 防爆破；仅已配置且已设密码时可用。
            if not _login_rate_ok():
                _audit("login_rate_limited", ip=ip)
                self._send(429, {"ok": False, "error": "尝试过于频繁（60 秒内最多 10 次）"})
                return
            cur = _read_token()
            stored = _read_password_hash()
            if not cur or not stored:
                self._send(200, {"ok": False, "error": "未设置密码"})
                return
            if _LOGIN_FAILS["n"] >= 5 and time.time() < _LOGIN_FAILS["until"]:
                _audit("login_locked", ip=ip)
                self._send(429, {"ok": False, "error": "连续失败已锁定，请 5 分钟后再试"})
                return
            ok = _check_password(str(req.get("password") or ""), stored)
            with _LOCK:  # R10.8h（红队 P3）：失败计数与锁定判定入锁，封并发旁路
                if not ok:
                    _LOGIN_FAILS["n"] += 1
                    if _LOGIN_FAILS["n"] >= 5:
                        _LOGIN_FAILS["until"] = time.time() + 300.0
                else:
                    _LOGIN_FAILS["n"] = 0
            if not ok:
                _audit("login", ok=False, ip=ip)
                self._send(200, {"ok": False, "error": "密码不正确"})
                return
            # R10.8（评审E P0-1）：不回旧明文——rotate 重签发新密钥（找回=重新签发，与注册对称）
            import secrets as _s2
            new_tok = _s2.token_hex(16)
            _write_token(new_tok)
            _audit("login_rotate", ok=True, ip=ip)
            self._send(200, {"ok": True, "token": new_tok})
            return
        if self.path == "/verify_password":
            # R10.8h（自毁教训）：只验证密码、绝不签发/轮换——供测试与"检查密码是否正确"使用。
            # 之前的测试真登录=每次 rotate=把管理员浏览器 Cookie 挤掉（自毁循环）。
            # R10.9（GLM-5.3 自检 P2-2 收口）：①补进程钥匙门——与 /verify /set 同面，
            # 沙箱经 host.docker.internal 连"问密码对不对"都不许；②失败与 /login 同桶
            # 计入 5 败锁——此前 verify_password 无限试错不锁定=爆破旁路（10/min 限频挡不住慢速爆破）。
            if not self._key_ok():
                _audit("verify_password_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            if not _login_rate_ok():
                _audit("verify_password_rate_limited", ip=ip)
                self._send(429, {"ok": False, "error": "尝试过于频繁"})
                return
            if _LOGIN_FAILS["n"] >= 5 and time.time() < _LOGIN_FAILS["until"]:
                _audit("verify_password_locked", ip=ip)
                self._send(429, {"ok": False, "error": "连续失败已锁定，请 5 分钟后再试"})
                return
            cur = _read_token()
            stored = _read_password_hash()
            ok = bool(cur and stored and _check_password(str(req.get("password") or ""), stored))
            with _LOCK:
                if not ok:
                    _LOGIN_FAILS["n"] += 1
                    if _LOGIN_FAILS["n"] >= 5:
                        _LOGIN_FAILS["until"] = time.time() + 300.0
                else:
                    _LOGIN_FAILS["n"] = 0  # 验对=证明持密码者本人，计数清零（与 /login 一致）
            _audit("verify_password", ok=ok, ip=ip)
            self._send(200, {"ok": ok})
            return
        if self.path == "/clear":
            if not self._key_ok():
                _audit("clear_no_key", ip=ip)
                self._send(403, {"ok": False, "error": "missing guard key"})
                return
            # R10.7b（hy4 P1-2）：未配置态的 clear 也要激活码证明——
            # 否则任何调用方可免凭证反复删密码+覆盖别人尚未使用的激活码（重置干扰）。
            cur = _read_token()
            if cur:
                if not _ck(str(req.get("token") or ""), cur):
                    _audit("clear_denied", ip=ip)
                    self._send(403, {"ok": False, "error": "清除需当前密钥"})
                    return
            else:
                expect = _bootstrap_read()
                if not expect or not _ck(expect, str(req.get("bootstrap") or "")):
                    _audit("clear_denied_unconfigured", ip=ip)
                    self._send(403, {"ok": False, "error": "未配置态清除需激活码证明"})
                    return
            _del_token()
            _del_password()
            _bootstrap_ensure()
            _audit("token_clear", ip=ip)
            self._send(200, {"ok": True, "cleared": True})
            return
        self._send(404, {"error": "not found"})


def _migrate_from_legacy() -> None:
    """一次性迁移：旧 .settings_secrets 里的 general.apiToken → guard DPAPI。
    迁移后从 json 删除该键（guard 成为唯一真源）；其余服务商密钥键原样保留。"""
    if _read_token():
        return  # guard 已有密钥
    legacy = Path(os.environ.get("M_GUARD_LEGACY_SECRETS", r"D:\m\secrets\.settings_secrets"))
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except Exception:
        return
    tok = str(data.get("general.apiToken") or "")
    if not tok:
        return
    _write_token(tok)
    data.pop("general.apiToken", None)
    try:
        tmp = legacy.with_name(legacy.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(legacy))
        _audit("migrated_from_legacy")
    except Exception as e:
        # R10.8（评审D）：json 写失败=旧明文残留 secrets 卷——回滚 bin，保单源一致
        _del_token()
        _audit("migration_rolled_back", err=type(e).__name__)
        return


if __name__ == "__main__":
    # R10.8b（红队 P2②）：先绑定端口再迁移——多实例双开时败者绑定失败即退出，
    # 不再出现"两进程都写 token.bin 后才抢端口"的损坏窗口
    _httpd = ThreadingHTTPServer(("127.0.0.1", _PORT), Handler)
    _migrate_from_legacy()
    if not _read_token():
        _bootstrap_ensure()
    # R10.8：hostcopy 挪路径后的衔接——守卫自己解得开 token.bin，把明文副本补写到新位置
    if _read_token() and not HOSTCOPY.exists():
        try:
            HOSTCOPY.write_text(_read_token(), encoding="utf-8")
            _audit("hostcopy_relocated")
        except OSError:
            pass
    _audit("guard_start", port=_PORT)
    _httpd.serve_forever()
