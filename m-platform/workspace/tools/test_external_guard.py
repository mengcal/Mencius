# -*- coding: utf-8 -*-
"""r58 external_guard 单测：v3 验收毒例 4 拒 1 过 + HKDF 稳定派生。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent.external_guard import validate_url, hkdf_subkey, ExternalUrlError  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


def rej(url, ports=(8899,)):
    try:
        validate_url(url, ports)
        return False
    except ExternalUrlError:
        return True


# ── v3 验收毒例：4 拒 ──
T("拒公网", rej("http://evil.example.com:8899/cb"))
T("拒私网 10.x", rej("http://10.0.0.5:8899/cb"))
T("拒云元数据 169.254", rej("http://169.254.169.254:8899/latest"))
T("拒非白名单端口", rej("http://127.0.0.1:9/cb", ports=(8899,)))
T("拒 file 协议", rej("file:///etc/passwd"))
T("拒 172.16 私网", rej("http://172.16.9.9:8899/x"))
# ── 1 过 ──
r = validate_url("http://127.0.0.1:8899/cb", (8899,))
T("环回+白名单端口通过", r["ip"] == "127.0.0.1" and r["port"] == 8899)
r6 = validate_url("http://[::1]:8899/cb", (8899,))
T("IPv6 环回通过", r6["ip"] in ("::1", "127.0.0.1") or ":" in str(r6["ip"]))
# localhost 变体（解析到环回=允许，解析到公网=拒——本机 hosts 环回应通过）
try:
    rl = validate_url("http://localhost:8899/cb", (8899,))
    T("localhost 解析环回则过", rl["ip"] in ("127.0.0.1", "::1"))
except ExternalUrlError:
    T("localhost 解析非环回被拒", True)

# ── HKDF ──
k1 = hkdf_subkey(b"master" * 8, "codebuddy-post")
k2 = hkdf_subkey(b"master" * 8, "codebuddy-post")
k3 = hkdf_subkey(b"master" * 8, "other-post")
T("同岗派生稳定", k1 == k2 and len(k1) == 32)
T("异岗子钥不同", k1 != k3)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
