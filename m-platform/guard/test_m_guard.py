"""test_m_guard.py — m-guard 守卫服务 单元测试（hy4 红队审查配套，任务 B；R10.6b 知夏终检版）。

运行：cd D:\\m\\guard && python test_m_guard.py   （225 断言，全绿为验收线）

纪律：
- 只 import D:\\m\\guard\\m_guard.py；所有落盘常量（TOKEN_BLOB / HOSTCOPY /
  AUDIT_LOG）在每次测试前 monkeypatch 到 tempfile 临时目录，测试后还原；
- sys.dont_write_bytecode = True，防止 import 时向 D:\\m\\guard\\__pycache__ 落 .pyc；
- tearDownModule 有真实文件"绊线"（Canary）：跑完必须证明没碰到真实数据。

命名约定：`*_CURR_BEHAVIOR` = 断言当前有问题的行为（钉死证据）；修复后改断言修后行为。
本轮已修并翻转断言的发现：F2(fail-open)/F6(体积+timeout)/F7(非dict崩溃+无审计)/
F9(空body清除)/F10(非原子写)/F17(chmod无效)。维持：F1(全局单桶，回环单管理员场景)、
F13(hostcopy 明文副本，icacls 缓解+待议消除)。
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# ── 只读加载守卫模块（r27 NOVA R5：路径=脚本同目录，GUARD_DIR 可显式覆盖）──
GUARD_DIR = Path(os.environ.get("GUARD_DIR") or Path(__file__).resolve().parent)
GUARD_SRC = GUARD_DIR / "m_guard.py"

# 必须在 import 之前设置：防止 SourceFileLoader 写 __pycache__ 进守卫目录
sys.dont_write_bytecode = True


def _load_guard():
    spec = importlib.util.spec_from_file_location("m_guard", str(GUARD_SRC))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法从 {GUARD_SRC} 加载 m_guard")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["m_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


mg = _load_guard()

# 测试夹具口令（非真实凭据，Mimosa 门：以常量注入避免字面量误报）
PW_OK = "hunter2pass"
PW_LONG = "a-long-password"
PW_OLD1 = "old-pass-alpha"
PW_NEW2 = "new-pass-beta"
PW_NEW3 = "new-pass-gamma"

# 每次测试都要改写的模块常量（R10.7b：含 password.bin——防测试写进真实 DPAPI 文件；
# R10.408：BOOTSTRAP_FILE 已随激活码机制退役）
_PATCHED_CONSTS = ("TOKEN_BLOB", "PASSWORD_BLOB", "HOSTCOPY", "AUDIT_LOG", "GUARD_KEY")

# ── 绊线（Canary）：证明测试没碰真实守卫数据 ─────────────────────
# 注意：D:\m\guard\token_audit.jsonl 故意不纳入——真实守卫服务正在运行，
# 它自己持续追加 verify 记录，纳入会误报。
_CANARY_PATHS = (
    GUARD_DIR / "token.bin",
    GUARD_DIR / "password.bin",
    GUARD_DIR / "hostcopy.token",
)


def _canary_snapshot():
    snap = {}
    for p in _CANARY_PATHS:
        try:
            st = p.stat()
            snap[str(p)] = (st.st_mtime_ns, st.st_size)
        except OSError:
            snap[str(p)] = None
    return snap


_CANARY_BEFORE = {}


def setUpModule():
    global _CANARY_BEFORE
    _CANARY_BEFORE = _canary_snapshot()


def tearDownModule():
    after = _canary_snapshot()
    diff = {k: (v, after[k]) for k, v in _CANARY_BEFORE.items() if after.get(k) != v}
    if diff:
        raise AssertionError(f"绊线告警：测试期间真实守卫文件被改动 -> {diff}")


# ── 可控时钟（_rate_ok 用 time.time()）──────────────────────────
class _FakeTime:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def time(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


# ── 基类：临时目录 + 常量重定向 + 静音 ───────────────────────────
class GuardTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._saved_consts = {n: getattr(mg, n) for n in _PATCHED_CONSTS}
        mg.TOKEN_BLOB = self.base / "token.bin"
        mg.PASSWORD_BLOB = self.base / "password.bin"
        mg.HOSTCOPY = self.base / ".api_token_hostcopy"
        mg.AUDIT_LOG = self.base / "token_audit.jsonl"
        self._saved_time = mg.time
        self.clock = _FakeTime()
        mg.time = self.clock
        mg._HITS.clear()
        self._saved_key = mg.GUARD_KEY
        mg.GUARD_KEY = "test-guard-key"  # R10.8：KEY 认证测试
        # R10.7b：/set 与 /login 独立限频桶也要隔离（模块级全局，跨用例不残留）
        getattr(mg, "_SET_HITS", []).clear()
        getattr(mg, "_LOGIN_HITS", []).clear()
        # 守卫 _audit 每次动作都 print，测试期静音（真实审计仍落临时 jsonl）
        self._mute = contextlib.redirect_stdout(io.StringIO())
        self._mute.__enter__()

    def tearDown(self):
        self._mute.__exit__(None, None, None)
        mg.time = self._saved_time
        for name, val in self._saved_consts.items():
            setattr(mg, name, val)
        mg._HITS.clear()
        getattr(mg, "_SET_HITS", []).clear()
        getattr(mg, "_LOGIN_HITS", []).clear()
        getattr(mg, "_LOGIN_FAILS", None) and mg._LOGIN_FAILS.update({"n": 0, "until": 0.0})
        getattr(mg, "_VERIFY_FAILS", None) and mg._VERIFY_FAILS.update({"n": 0, "until": 0.0})
        self._tmp.cleanup()

    # 便捷断言/工具
    def set_token(self, value):
        mg._write_token(value)


class HttpTestCase(GuardTestCase):
    """把 Handler 起在 127.0.0.1 随机端口上，走真实 HTTP。"""

    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), mg.Handler)
        self.port = self.srv.server_address[1]
        self._thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self._thread.join(timeout=5)
        self.srv.server_close()
        super().tearDown()

    def get(self, path, key=True):
        hdrs = {"X-Guard-Key": mg.GUARD_KEY} if key else {}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def post(self, path, payload=None, raw=None, key=True):
        """raw 不为 None 时按原始字节发（用于畸形 JSON 测试）。key=False 测无钥匙 403。"""
        body = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        if key:
            hdrs["X-Guard-Key"] = mg.GUARD_KEY
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            headers=hdrs,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except Exception as e:  # 连接被重置/无响应（未捕获的服务端异常）
            return None, {"exc": type(e).__name__}


# ══════════════════════════════════════════════════════════════
# 1. _ck 常数时间比对
# ══════════════════════════════════════════════════════════════
class TestCk(GuardTestCase):
    def test_same_ascii(self):
        self.assertTrue(mg._ck("abc123", "abc123"))

    def test_different_ascii(self):
        self.assertFalse(mg._ck("abc123", "abc124"))

    def test_prefix_is_not_match(self):
        self.assertFalse(mg._ck("abc", "abcd"))
        self.assertFalse(mg._ck("abcd", "abc"))

    def test_case_sensitive(self):
        self.assertFalse(mg._ck("Token", "token"))

    def test_non_ascii_equal(self):
        self.assertTrue(mg._ck("米娅的管理员令牌", "米娅的管理员令牌"))

    def test_non_ascii_differ(self):
        self.assertFalse(mg._ck("米娅的管理员令牌", "米娅的管理员令脾"))

    def test_emoji_equal_and_differ(self):
        self.assertTrue(mg._ck("tok🔑🛡", "tok🔑🛡"))
        self.assertFalse(mg._ck("tok🔑🛡", "tok🔑"))

    def test_non_str_coerced_via_str(self):
        self.assertTrue(mg._ck(123, "123"))
        self.assertTrue(mg._ck(["a"], "['a']"))

    def test_none_and_empty_normalize_to_empty(self):
        """_ck 自身把 None/"" 归一为 ""——因此 /verify 层必须先判
        _read_token() 为空即拒（F2 修复），本行为由上层保证 fail-closed。"""
        self.assertTrue(mg._ck(None, ""))
        self.assertTrue(mg._ck("", None))
        self.assertTrue(mg._ck(None, None))
        self.assertTrue(mg._ck("", ""))

    def test_returns_bool_not_truthy(self):
        self.assertIs(mg._ck("a", "a"), True)
        self.assertIs(mg._ck("a", "b"), False)


# ══════════════════════════════════════════════════════════════
# 2. _rate_ok 限频
# ══════════════════════════════════════════════════════════════
class TestRateLimit(GuardTestCase):
    def test_first_300_allowed(self):
        self.assertTrue(all(mg._rate_ok() for _ in range(300)))

    def test_301st_blocked(self):
        for _ in range(300):
            mg._rate_ok()
        self.assertFalse(mg._rate_ok())

    def test_window_expiry_frees_slots(self):
        for _ in range(300):
            mg._rate_ok()
        self.clock.advance(61.0)
        self.assertTrue(mg._rate_ok())
        self.assertEqual(len(mg._HITS), 1)  # 旧记录被整体剪掉

    def test_partial_window_only_prunes_expired(self):
        for _ in range(10):
            mg._rate_ok()
        self.clock.advance(30.0)
        for _ in range(5):
            mg._rate_ok()
        self.clock.advance(31.0)  # 前 10 条过期、后 5 条仍有效
        self.assertTrue(mg._rate_ok())
        self.assertEqual(len(mg._HITS), 6)

    def test_bucket_is_global_not_per_ip(self):
        """F1（维持）：_HITS 是模块级单桶——回环单管理员场景，按 IP 分桶暂无必要。"""
        for _ in range(300):
            mg._rate_ok()
        self.assertFalse(mg._rate_ok())

    def test_rate_limit_does_not_leak_hits_on_rejection(self):
        for _ in range(300):
            mg._rate_ok()
        before = len(mg._HITS)
        mg._rate_ok()
        self.assertEqual(len(mg._HITS), before)  # 被拒时不记账（否则永久封死）


# ══════════════════════════════════════════════════════════════
# 3. DPAPI protect → unprotect 往返
# ══════════════════════════════════════════════════════════════
@unittest.skipUnless(sys.platform == "win32", "DPAPI 仅 Windows")
class TestDpapiRoundTrip(GuardTestCase):
    def test_ascii(self):
        self.assertEqual(mg._dpapi_unprotect(mg._dpapi_protect(b"hello-guard")), b"hello-guard")

    def test_utf8_multibyte(self):
        raw = "米娅的令牌🔑".encode("utf-8")
        self.assertEqual(mg._dpapi_unprotect(mg._dpapi_protect(raw)), raw)

    def test_binary_1kb(self):
        raw = bytes(range(256)) * 4
        self.assertEqual(mg._dpapi_unprotect(mg._dpapi_protect(raw)), raw)

    def test_ciphertext_differs_from_plaintext(self):
        raw = b"super-secret-token"
        blob = mg._dpapi_protect(raw)
        self.assertNotEqual(blob, raw)
        self.assertNotIn(raw, blob)

    def test_two_protects_of_same_input_differ(self):
        """DPAPI 带随机 salt，同一明文两次加密结果不同（防密文比对）。"""
        self.assertNotEqual(mg._dpapi_protect(b"same"), mg._dpapi_protect(b"same"))

    def test_unprotect_garbage_raises_oserror(self):
        with self.assertRaises(OSError):
            mg._dpapi_unprotect(b"this-is-not-a-dpapi-blob")

    def test_empty_payload(self):
        try:
            out = mg._dpapi_unprotect(mg._dpapi_protect(b""))
        except OSError as e:
            self.skipTest(f"本机 DPAPI 拒绝空载荷：{e}")
        self.assertEqual(out, b"")


# ══════════════════════════════════════════════════════════════
# 4. 激活码机制退役（R10.408 爸爸令："注册之前不该上锁"）——回归钉
# ══════════════════════════════════════════════════════════════
class TestBootstrapRetired(GuardTestCase):
    def test_guard_source_has_no_bootstrap(self):
        """激活码机制整体废除：守卫源码不得再出现 bootstrap 字样（防复活）。"""
        src = GUARD_SRC.read_text(encoding="utf-8")
        self.assertNotIn("bootstrap", src.lower())

    def test_hostcopy_still_uses_icacls_not_chmod(self):
        """F17 教训保留：icacls 收紧 ACL 的机制仍在（现由 _write_hostcopy 使用）。"""
        src = GUARD_SRC.read_text(encoding="utf-8")
        self.assertIn("icacls", src)
        self.assertNotIn("os.chmod", src)


# ══════════════════════════════════════════════════════════════
# 5. /set 首设（R10.408：注册窗口开放，谁先注册谁是主人）
# ══════════════════════════════════════════════════════════════
class TestSetFirstInstall(HttpTestCase):
    def test_first_set_open_succeeds(self):
        """无激活码首设直接成功——注册前不上锁。"""
        code, body = self.post("/set", {"token": "T-first"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(mg._read_token(), "T-first")

    def test_first_set_with_password(self):
        code, body = self.post("/set", {"token": "T-p", "password": PW_OK})
        self.assertEqual(code, 200)
        self.assertTrue(self.post("/login", {"password": PW_OK})[1]["ok"])

    def test_first_set_short_password_400(self):
        code, body = self.post("/set", {"token": "T-a", "password": "short"})
        self.assertEqual(code, 400)
        self.assertFalse(mg.TOKEN_BLOB.exists(), "拒绝则一字不写")

    def test_first_set_ignores_stale_bootstrap_field(self):
        """旧调用方仍带 bootstrap 字段=被忽略（机制退役，不再 403）。"""
        code, _ = self.post("/set", {"token": "T-x", "bootstrap": "WRONG"})
        self.assertEqual(code, 200)

    def test_empty_token_400(self):
        code, body = self.post("/set", {"token": ""})
        self.assertEqual(code, 400)
        self.assertIn("token required", json.dumps(body, ensure_ascii=False))

    def test_second_set_requires_current(self):
        """注册完门就焊死：第二个注册者没有 current 证明=403（轮换语义）。"""
        self.post("/set", {"token": "T-first"})
        code, _ = self.post("/set", {"token": "T-evil"})
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "T-first", "拒绝后密钥原样")
        code, _ = self.post("/set", {"token": "T2", "current": "T-first"})
        self.assertEqual(code, 200)


# ══════════════════════════════════════════════════════════════
# 5b. 首设原子化（R10.7b hy4 P1-1 死锁修复）
# ══════════════════════════════════════════════════════════════
class TestFirstSetAtomic(HttpTestCase):
    def test_first_set_with_password_then_login(self):
        """单请求=写密钥+写密码同持锁段；随后密码找回=重签发新密钥。"""
        code, body = self.post("/set", {"token": "T-a", "password": PW_OK})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(mg._read_token(), "T-a")
        code, body = self.post("/login", {"password": PW_OK})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertNotEqual(body["token"], "T-a", "找回=重签发，不回吐旧值")
        self.assertEqual(mg._read_token(), body["token"])

    def test_first_set_short_password_400_keeps_state(self):
        """校验先于写入：密码太短被拒时 token 不落盘。"""
        code, body = self.post("/set", {"token": "T-a", "password": "short"})
        self.assertEqual(code, 400)
        self.assertFalse(mg.TOKEN_BLOB.exists())

    def test_set_password_requires_current(self):
        """R10.7b：/set_password 只认当前密钥（或旧密码）证明。"""
        self.set_token("T-x")
        code, _ = self.post("/set_password", {"password": PW_LONG, "current": "WRONG"})
        self.assertEqual(code, 403)
        code, _ = self.post("/set_password", {"password": PW_LONG, "current": "T-x"})
        self.assertEqual(code, 200)
        self.assertTrue(self.post("/login", {"password": PW_LONG})[1]["ok"])

    def test_login_rate_limited(self):
        self.post("/set", {"token": "T-a", "password": PW_LONG})
        for _ in range(10):
            self.post("/login", {"password": "wrong"})
        code, body = self.post("/login", {"password": PW_LONG})
        self.assertEqual(code, 429)

    def test_set_rate_limited(self):
        for _ in range(10):
            self.post("/set", {"token": "T"})
        code, _ = self.post("/set", {"token": "T-a"})
        self.assertEqual(code, 429)


class TestGuardKeyAndRotate(HttpTestCase):
    def setUp(self):
        super().setUp()
        self.set_token("OLD-TOK")

    def test_no_key_verify_403(self):
        code, _ = self.post("/verify", {"token": "OLD-TOK"}, key=False)
        self.assertEqual(code, 403)

    def test_no_key_set_403(self):
        code, _ = self.post("/set", {"token": "X"}, key=False)
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "OLD-TOK", "拒绝后密钥原样")

    def test_no_key_clear_403(self):
        code, _ = self.post("/clear", {"token": "OLD-TOK"}, key=False)
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "OLD-TOK")

    def test_status_is_key_free(self):
        self.assertEqual(self.get("/status", key=False)[0], 200)

    def test_login_rotates_not_replays(self):
        """千问 P0-1 已修：/login 不回旧明文——rotate 重签发新密钥并刷新 hostcopy。"""
        code, body = self.post("/set", {"token": "NEW-TOK", "current": "OLD-TOK", "password": "long-enough-pw"})
        self.assertEqual(code, 200)
        code, body = self.post("/login", {"password": "long-enough-pw"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertNotEqual(body["token"], "NEW-TOK", "找回=重签发，绝不回吐旧明文")
        self.assertEqual(mg._read_token(), body["token"])
        self.assertEqual(mg.HOSTCOPY.read_text(encoding="utf-8"), body["token"])

    def test_password_min_length_8(self):
        code, body = self.post("/set", {"token": "T1", "current": "OLD-TOK", "password": "shortpw"})
        self.assertEqual(code, 400)
        self.assertEqual(mg._read_token(), "OLD-TOK", "原子段内失败密钥原样")

    def test_change_password_requires_old_password(self):
        """R10.8d（爸爸："怎么修改密码"）+r27 评审 P1-1 分层定稿：
        守卫层保留两条证明——①旧密码 ②当前密钥（宿主救急通道 reset_password.cmd
        直连本层，物理访问=信任锚）。浏览器面在 office 层收紧：/auth/set_password
        不再代转 current（持 Cookie 的 XSS 脚本读得到钥匙发得出请求，但经 office
        时只剩旧密码一条路——2026-09-23 CB 评审 P1-1 修复，本层测试口径同步）。
        无任何证明=403，旧密码错=403。"""
        self.post("/set", {"token": "T1", "current": "OLD-TOK", "password": PW_OLD1})
        # 无任何证明 → 403
        code, _ = self.post("/set_password", {"password": PW_NEW2})
        self.assertEqual(code, 403)
        # 旧密码错（且无 current）→ 403
        code, _ = self.post("/set_password", {"password": PW_NEW2, "old_password": "WRONG"})
        self.assertEqual(code, 403)
        # 仅当前密钥证明（宿主直连场景）→ 成功，旧密码 /login 失效
        code, _ = self.post("/set_password", {"password": PW_NEW2, "current": "T1"})
        self.assertEqual(code, 200)
        self.assertFalse(self.post("/login", {"password": PW_OLD1})[1]["ok"])
        self.assertTrue(self.post("/login", {"password": PW_NEW2})[1]["ok"])
        # 仅旧密码证明（前端表单路径）→ 成功
        code, _ = self.post("/set_password", {"password": PW_NEW3, "old_password": PW_NEW2})
        self.assertEqual(code, 200)
        self.assertTrue(self.post("/login", {"password": PW_NEW3})[1]["ok"])

    def test_first_set_password_write_failure_rolls_back_token(self):
        """r27 评审 P2-4（CB）：首设密码写失败=回滚 token，不留"有密钥无密码"半注册态。"""
        mg._del_token()  # 本类 setUp 已配 OLD-TOK——回滚测试必须在未配置态测首设分支
        orig = mg._write_password_hash
        try:
            mg._write_password_hash = lambda h: (_ for _ in ()).throw(OSError("模拟 DPAPI 写炸"))
            code, _ = self.post("/set", {"token": "T-half", "password": PW_OK})
            self.assertIn(code, (400, 500))
            self.assertEqual(mg._read_token(), "", "半完成态必须回滚——密钥不得留下")
        finally:
            mg._write_password_hash = orig
        # 恢复后正常注册不受影响
        code, _ = self.post("/set", {"token": "T-ok", "password": PW_OK})
        self.assertEqual(code, 200)

    def test_verify_password_key_gate_and_lockout(self):
        """R10.9（GLM-5.3 自检 P2-2 收口）：/verify_password 补进程钥匙门+5 败锁——
        此前该端点无钥匙门（沙箱可无限问"密码对不对"）且失败不计数（爆破旁路）。
        r30 Veda F4：锁桶改【独立】（_VERIFY_FAILS），不再与 /login 共桶——
        共桶时持 token 者填 5 次错密码即可锁死登录通道（DoS 牵连）。"""
        self.post("/set", {"token": "T1", "current": "OLD-TOK", "password": "long-enough-pw"})
        # 无进程钥匙 → 403（与 /verify /set /set_password 同面）
        code, _ = self.post("/verify_password", {"password": "long-enough-pw"}, key=False)
        self.assertEqual(code, 403)
        # 对密码（带钥匙）→ 200
        code, body = self.post("/verify_password", {"password": "long-enough-pw"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        # 5 次错密码 → verify 独立桶锁定；/login 不受牵连（r30 Veda F4 分桶断言）
        for _ in range(5):
            self.post("/verify_password", {"password": "wrong-wrong-wrong"})
        code, _ = self.post("/verify_password", {"password": "long-enough-pw"})
        self.assertEqual(code, 429, "verify_password 失败计入自身 5 败锁（r30 独立桶）")
        code, _ = self.post("/login", {"password": "long-enough-pw"})
        self.assertEqual(code, 200, "r30 Veda F4：独立桶——verify 打满不锁 /login")

    def test_login_failure_lockout(self):
        self.post("/set", {"token": "T1", "current": "OLD-TOK", "password": "long-enough-pw"})
        for _ in range(5):
            self.post("/login", {"password": "wrong-wrong-wrong"})
        code, body = self.post("/login", {"password": "long-enough-pw"})
        self.assertEqual(code, 429, "连续 5 次失败后锁定（Eve P2-2）")

    def test_no_key_login_403(self):
        """R10.11（Eve P2）：/login 是唯一能签发新管理员密钥的端点，补钥匙门时
        门与断言同批落地（Eve："新门必配断言"——门与绊线同 PR）。"""
        self.post("/set", {"token": "T1", "current": "OLD-TOK", "password": "long-enough-pw"})
        code, body = self.post("/login", {"password": "long-enough-pw"}, key=False)
        self.assertEqual(code, 403)
        self.assertEqual(body.get("error"), "missing guard key")


# ══════════════════════════════════════════════════════════════
# 6. /verify
# ══════════════════════════════════════════════════════════════
class TestVerify(HttpTestCase):
    def setUp(self):
        super().setUp()
        self.set_token("T-verify")

    def test_correct_token(self):
        code, body = self.post("/verify", {"token": "T-verify"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])

    def test_wrong_token(self):
        code, body = self.post("/verify", {"token": "nope"})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])

    def test_missing_token_field(self):
        code, body = self.post("/verify", {})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])

    def test_null_token_field(self):
        code, body = self.post("/verify", {"token": None})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])

    def test_non_ascii_token_compares_safely(self):
        self.assertFalse(self.post("/verify", {"token": "米娅🔑"})[1]["ok"])
        self.set_token("米娅🔑")
        self.assertTrue(self.post("/verify", {"token": "米娅🔑"})[1]["ok"])
        self.assertFalse(self.post("/verify", {"token": "米娅"})[1]["ok"])

    def test_never_returns_plaintext(self):
        _, body = self.post("/verify", {"token": "T-verify"})
        self.assertEqual(set(body.keys()), {"ok"})
        self.assertNotIn("T-verify", json.dumps(body, ensure_ascii=False))

    def test_rate_limited_returns_429(self):
        mg._HITS[:] = [self.clock.time()] * 300  # 直接把全局桶填满
        code, body = self.post("/verify", {"token": "T-verify"})
        self.assertEqual(code, 429)
        self.assertFalse(body["ok"])
        self.assertIn("rate limited", json.dumps(body))

    def test_empty_token_when_unconfigured_is_fail_closed(self):
        """F2（P0）已修：未配置态 _read_token()=="" 时 /verify 一律 False（fail-closed），
        不再出现"空令牌==空密钥→放行"。"""
        mg._del_token()
        self.assertEqual(mg._read_token(), "")
        code, body = self.post("/verify", {"token": ""})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"], "修复后：空令牌必须拒绝（fail-closed）")

    def test_unknown_path_404(self):
        self.assertEqual(self.post("/nope", {"token": "x"})[0], 404)
        self.assertEqual(self.get("/nope")[0], 404)


# ══════════════════════════════════════════════════════════════
# 7. /set 轮换
# ══════════════════════════════════════════════════════════════
class TestRotate(HttpTestCase):
    def setUp(self):
        super().setUp()
        self.set_token("OLD-TOK")

    def test_rotate_with_correct_current(self):
        code, body = self.post("/set", {"token": "NEW-TOK", "current": "OLD-TOK"})
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(mg._read_token(), "NEW-TOK")
        self.assertEqual(mg.HOSTCOPY.read_text(encoding="utf-8"), "NEW-TOK")

    def test_rotate_with_wrong_current_403(self):
        code, body = self.post("/set", {"token": "EVIL", "current": "WRONG"})
        self.assertEqual(code, 403)
        self.assertFalse(body["ok"])
        self.assertEqual(mg._read_token(), "OLD-TOK", "拒绝后密钥必须原样")

    def test_rotate_without_current_403(self):
        code, _ = self.post("/set", {"token": "EVIL"})
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "OLD-TOK")

    def test_rotate_with_empty_current_403(self):
        code, _ = self.post("/set", {"token": "EVIL", "current": ""})
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "OLD-TOK")

    def test_rotate_to_empty_token_400(self):
        code, _ = self.post("/set", {"token": "   ", "current": "OLD-TOK"})
        self.assertEqual(code, 400)

    def test_rotate_refreshes_hostcopy_plaintext(self):
        """F13（维持+icacls 缓解）：明文副本同步刷新，供宿主测试脚本使用。"""
        self.post("/set", {"token": "NEW-TOK", "current": "OLD-TOK"})
        self.assertTrue(mg.HOSTCOPY.exists())
        self.assertEqual(mg.HOSTCOPY.read_text(encoding="utf-8"), "NEW-TOK")


# ══════════════════════════════════════════════════════════════
# 8. /clear
# ══════════════════════════════════════════════════════════════
class TestClear(HttpTestCase):
    def test_clear_unconfigured_is_noop(self):
        """R10.408：未配置态清除=无操作（没东西可清，也不再写激活码）。"""
        self.assertFalse(mg.TOKEN_BLOB.exists())
        code, body = self.post("/clear", {"token": "anything"})
        self.assertEqual(code, 200)
        self.assertFalse(body["cleared"])

    def test_clear_with_wrong_token_403(self):
        self.set_token("T-clear")
        code, body = self.post("/clear", {"token": "WRONG"})
        self.assertEqual(code, 403)
        self.assertFalse(body["ok"])
        self.assertEqual(mg._read_token(), "T-clear")

    def test_clear_with_empty_token_when_configured_403(self):
        self.set_token("T-clear")
        code, _ = self.post("/clear", {"token": ""})
        self.assertEqual(code, 403)
        self.assertEqual(mg._read_token(), "T-clear")

    def test_clear_with_correct_token(self):
        self.set_token("T-clear")
        code, body = self.post("/clear", {"token": "T-clear"})
        self.assertEqual(code, 200)
        self.assertTrue(body["cleared"])
        self.assertFalse(mg.TOKEN_BLOB.exists())
        self.assertFalse(mg.HOSTCOPY.exists())
        self.assertEqual(mg._read_token(), "")

    def test_clear_then_first_set_roundtrip(self):
        """清除=回到注册窗口，直接重新首设（R10.408 无激活码）。"""
        self.set_token("T1")
        self.post("/clear", {"token": "T1"})
        code, _ = self.post("/set", {"token": "T2"})
        self.assertEqual(code, 200)
        self.assertEqual(mg._read_token(), "T2")

    def test_clear_with_empty_body_is_400(self):
        """F9 已修：空 body 不再被当 {} 视作"未配置态无证明清除"——一律 400。"""
        code, body = self.post("/clear", raw=b"")
        self.assertEqual(code, 400)


# ══════════════════════════════════════════════════════════════
# 9. /status
# ══════════════════════════════════════════════════════════════
class TestStatus(HttpTestCase):
    def test_status_unconfigured(self):
        code, body = self.get("/status")
        self.assertEqual(code, 200)
        self.assertFalse(body["configured"])
        self.assertEqual(body["service"], "m-guard")

    def test_status_configured(self):
        self.set_token("T-status")
        code, body = self.get("/status")
        self.assertEqual(code, 200)
        self.assertTrue(body["configured"])

    def test_status_flips_after_clear(self):
        self.set_token("T-status")
        self.assertTrue(self.get("/status")[1]["configured"])
        self.post("/clear", {"token": "T-status"})
        self.assertFalse(self.get("/status")[1]["configured"])

    def test_status_leaks_no_token(self):
        self.set_token("SUPER-SECRET")
        raw = json.dumps(self.get("/status")[1], ensure_ascii=False)
        self.assertNotIn("SUPER-SECRET", raw)

    def test_bootstrap_status_endpoint_retired(self):
        """R10.408：/bootstrap/status 端点已随激活码退役——404。"""
        self.assertEqual(self.get("/bootstrap/status")[0], 404)


# ══════════════════════════════════════════════════════════════
# 10. hostcopy 明文副本 + 审计
# ══════════════════════════════════════════════════════════════
class TestHostcopy(GuardTestCase):
    def test_write_token_lands_plaintext_hostcopy(self):
        """F13（维持+icacls 缓解）：明文副本落盘供宿主测试脚本用，ACL 已收紧。"""
        self.set_token("PLAINTEXT-ON-DISK")
        self.assertTrue(mg.HOSTCOPY.exists())
        self.assertEqual(mg.HOSTCOPY.read_text(encoding="utf-8"), "PLAINTEXT-ON-DISK")

    def test_hostcopy_failure_is_audited_not_fatal(self):
        mg.HOSTCOPY = self.base / "missing_dir" / "hostcopy"
        with contextlib.redirect_stderr(io.StringIO()):
            self.set_token("T")  # 不抛异常
        self.assertTrue(mg.TOKEN_BLOB.exists())
        lines = mg.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("hostcopy_failed" in ln for ln in lines))

    def test_del_token_removes_both(self):
        self.set_token("T")
        self.assertTrue(mg.TOKEN_BLOB.exists() and mg.HOSTCOPY.exists())
        mg._del_token()
        self.assertFalse(mg.TOKEN_BLOB.exists())
        self.assertFalse(mg.HOSTCOPY.exists())

    def test_del_token_when_absent_is_noop(self):
        mg._del_token()
        self.assertFalse(mg.TOKEN_BLOB.exists())


class TestAudit(GuardTestCase):
    def test_audit_writes_parseable_jsonl(self):
        mg._audit("unit_test", foo="bar")
        lines = mg.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["action"], "unit_test")
        self.assertEqual(rec["foo"], "bar")
        self.assertIn("ts", rec)

    def test_audit_appends(self):
        for i in range(3):
            mg._audit(f"a{i}")
        self.assertEqual(len(mg.AUDIT_LOG.read_text(encoding="utf-8").splitlines()), 3)

    def test_audit_truncates_extra_values_to_80_chars(self):
        mg._audit("unit_test", big="x" * 500)
        rec = json.loads(mg.AUDIT_LOG.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(len(rec["big"]), 80)

    def test_audit_swallows_oserror_silently(self):
        """审计写失败静默 pass（观测面不挡闸门），服务照常响应。"""
        mg.AUDIT_LOG = self.base  # 一个目录：open(dir, "a") → IsADirectoryError
        mg._audit("should_not_raise")  # 不抛异常即为通过

    def test_audit_never_records_the_token(self):
        self.set_token("NEVER-LOG-ME")
        mg._audit("verify", ok=True, ip="127.0.0.1")
        text = mg.AUDIT_LOG.read_text(encoding="utf-8")
        self.assertNotIn("NEVER-LOG-ME", text)


# ══════════════════════════════════════════════════════════════
# 11. HTTP 解析健壮性
# ══════════════════════════════════════════════════════════════
class TestHttpRobustness(HttpTestCase):
    def setUp(self):
        super().setUp()
        # 先置一个密钥：否则未配置态下 F2 修复后各"应判失败"断言全部由 fail-closed 达成
        self.set_token("T-robust")

    def test_malformed_json_returns_400(self):
        code, body = self.post("/verify", raw=b"{not json")
        self.assertEqual(code, 400)
        self.assertEqual(body["error"], "bad request")

    def test_empty_body_is_rejected(self):
        """F9 配套：空 body 一律 400（不再被当 {} 解析）。"""
        code, body = self.post("/verify", raw=b"")
        self.assertEqual(code, 400)

    def test_non_dict_json_returns_400(self):
        """F7 已修：顶层非 dict 的合法 JSON 返回 400（do_POST 顶层兜底），不再崩线程。"""
        code, body = self.post("/verify", raw=b"[1,2,3]")
        self.assertEqual(code, 400)

    def test_bare_number_json_returns_400(self):
        code, _ = self.post("/verify", raw=b"123")
        self.assertEqual(code, 400)

    def test_bad_request_writes_audit_record(self):
        """F7 加重版已修：畸形请求现在落 bad_json 审计，可取证。"""
        self.post("/verify", raw=b'"just a string"')
        self.assertTrue(mg.AUDIT_LOG.exists())
        self.assertIn("bad_json", mg.AUDIT_LOG.read_text(encoding="utf-8"))

    def test_content_length_has_cap(self):
        """F6 已修：Content-Length 上限 64KB，声明多大就拒多大。"""
        src = GUARD_SRC.read_text(encoding="utf-8")
        self.assertIn("65536", src)
        self.assertIn("body too large", src)

    def test_token_blob_write_is_atomic(self):
        """F10 已修：_write_token 改 tmp+os.replace 原子写 + _LOCK 串行——
        写一半崩溃/并发交叉不再产生损坏的 token.bin。"""
        src = GUARD_SRC.read_text(encoding="utf-8")
        body = src.split("def _write_token", 1)[1].split("def _write_hostcopy", 1)[0]
        self.assertIn("os.replace", body)
        self.assertIn(".tmp", body)

    def test_server_has_socket_timeout(self):
        """F6 已修：Handler.timeout=30，慢速连接不再占死线程。"""
        self.assertEqual(mg.Handler.timeout, 30)

    def test_non_ascii_json_body(self):
        code, body = self.post("/verify", {"token": "米娅🔑"})
        self.assertEqual(code, 200)
        self.assertFalse(body["ok"])


# ══════════════════════════════════════════════════════════════
# 12. 迁移逻辑
# ══════════════════════════════════════════════════════════════
class TestMigrateFromLegacy(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.legacy = self.base / ".settings_secrets"
        self._saved_env = os.environ.get("M_GUARD_LEGACY_SECRETS")
        os.environ["M_GUARD_LEGACY_SECRETS"] = str(self.legacy)

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("M_GUARD_LEGACY_SECRETS", None)
        else:
            os.environ["M_GUARD_LEGACY_SECRETS"] = self._saved_env
        super().tearDown()

    def test_migrates_api_token_and_keeps_other_keys(self):
        self.legacy.write_text(
            json.dumps({"general.apiToken": "LEGACY-TOK", "search.metasoKey": "KEEP-ME"}),
            encoding="utf-8",
        )
        mg._migrate_from_legacy()
        self.assertEqual(mg._read_token(), "LEGACY-TOK")
        self.assertEqual(mg.HOSTCOPY.read_text(encoding="utf-8"), "LEGACY-TOK")
        after = json.loads(self.legacy.read_text(encoding="utf-8"))
        self.assertNotIn("general.apiToken", after)
        self.assertEqual(after["search.metasoKey"], "KEEP-ME")

    def test_migration_is_idempotent(self):
        self.legacy.write_text(json.dumps({"general.apiToken": "LEGACY-TOK"}), encoding="utf-8")
        mg._migrate_from_legacy()
        mg._migrate_from_legacy()
        self.assertEqual(mg._read_token(), "LEGACY-TOK")

    def test_migration_skipped_when_guard_already_has_token(self):
        self.set_token("ALREADY")
        self.legacy.write_text(json.dumps({"general.apiToken": "LEGACY-TOK"}), encoding="utf-8")
        mg._migrate_from_legacy()
        self.assertEqual(mg._read_token(), "ALREADY")
        after = json.loads(self.legacy.read_text(encoding="utf-8"))
        self.assertEqual(after["general.apiToken"], "LEGACY-TOK", "不应被动过")

    def test_no_legacy_file_is_noop(self):
        mg._migrate_from_legacy()  # 不抛异常
        self.assertEqual(mg._read_token(), "")

    def test_legacy_without_api_token_is_noop(self):
        self.legacy.write_text(json.dumps({"search.metasoKey": "K"}), encoding="utf-8")
        mg._migrate_from_legacy()
        self.assertEqual(mg._read_token(), "")

    def test_corrupt_legacy_json_is_noop(self):
        self.legacy.write_text("{ broken", encoding="utf-8")
        mg._migrate_from_legacy()
        self.assertEqual(mg._read_token(), "")

    def test_legacy_tmp_file_is_cleaned_up_by_replace(self):
        self.legacy.write_text(json.dumps({"general.apiToken": "L"}), encoding="utf-8")
        mg._migrate_from_legacy()
        self.assertFalse(self.legacy.with_name(self.legacy.name + ".tmp").exists())


# ══════════════════════════════════════════════════════════════
# 13. 线程安全
# ══════════════════════════════════════════════════════════════
class TestConcurrency(GuardTestCase):
    def test_concurrent_write_token_leaves_a_readable_value(self):
        """F10 已修（原子写+_LOCK）：并发下最终值是写入集合中的某一个，文件不损坏。"""
        values = [f"tok-{i:02d}" for i in range(8)]

        def worker(v):
            for _ in range(10):
                mg._write_token(v)

        threads = [threading.Thread(target=worker, args=(v,)) for v in values]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        final = mg._read_token()
        self.assertIn(final, values, f"最终值应落在写入集合内，实际={final!r}")

    def test_concurrent_audit_does_not_corrupt_jsonl(self):
        def worker(i):
            for _ in range(20):
                mg._audit("concurrent", i=i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        lines = mg.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 120)
        for ln in lines:
            json.loads(ln)  # 每行都必须是完整 JSON


if __name__ == "__main__":
    unittest.main(verbosity=2)
