"""
office.core —— 纯函数/常量公共层（无路由、无 app 依赖；router 只从这里与外部模块取公共件，禁止反向 import app）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :24-28     BASE 与 .env 加载（原文件没有 _load_dotenv_mini 函数；.env 加载保持"import 即生效"的启动副作用，
             放本层可保证任何 router / settings_mgr 读 env 之前 .env 已就位）
- :51-59     _secrets_dir（宿主侧 secrets 卷目录）
- :62-70     _ck（常数时间比对统一入口）
- :743-752   _rate_ok（通用滑动窗口）
- :931-948   _ROTATE_BYTES / _rotate_log（账本 .1/.2/.3 三代滚动）
- :1150-1152 _JSONResp / _RawResp 导入别名下沉本层（各 router 共用；:1152 裸 `from fastapi import Response` 原样保留）
- :1202-1217 _token_audit（token_admin 与 misc 的 /approvals 共用 → 公共层）
- :1284-1297 _presented_token（app.py 守卫与 token_admin 共用 → 公共层）

【路径基准变更】原 office.py 位于 workplatform 根，BASE = Path(__file__).parent 即 workplatform 根；
包化后本文件位于 <workplatform>/office/ 内，故 BASE 上跳一级（parent.parent），语义保持"workplatform 根"。
"""
import os
import time

from pathlib import Path

from dotenv import load_dotenv

from fastapi import Response  # 原 :1152（原样保留）
from fastapi.responses import Response as _RawResp  # R10.8c：守卫 4xx 原样透传（原 :1150）
from starlette.responses import JSONResponse as _JSONResp  # 原 :1160

BASE = Path(__file__).resolve().parent.parent  # workplatform 根（原 :26；包化后上跳一级）

# ---- 加载 .env（模型 key） ----
load_dotenv(BASE / ".env")
print("[office] STEP0.5 .env loaded", flush=True)


# ===== R10 修四①：宿主侧 secrets 卷目录（被审计方摸不到的地方）=====
# 账本/激活码一律挪到这个目录：沙箱与工人岗进程不可达 secrets 卷，因此改不动账本、读不到激活码。
# R10.2（hy4 ②-1，实测坐实）：env MIA_SECRETS_PATH 的真语义=密钥【文件】路径
# （settings_mgr:24 同用此值且按文件读写）——旧实现把文件路径当目录返回，
# 生产下 .token_bootstrap/两本账全落在 "/data/secrets/.settings_secrets/xxx" 这种不可能路径上，
# mkdir 必炸→激活码静默不生成→首设永久不可用、账本形同虚设。取 .parent 才是所在目录。
def _secrets_dir() -> Path:
    p = os.environ.get("MIA_SECRETS_PATH", "").strip()
    return (Path(p).parent if p else (BASE.parent / "secrets"))


def _ck(a: str, b: str) -> bool:
    """R10.2（hy4 ③-10/②-6 同族）：常数时间比对统一入口。
    hmac.compare_digest 收两个非 ASCII str 会抛 TypeError（500 而非拒）——统一转 bytes 再比，
    bytes 比对永不抛；任何异常一律按"不匹配"处理（fail-closed）。"""
    import hmac as _h
    try:
        return _h.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))
    except Exception:
        return False


def _rate_ok(hits: list, window: float, cap: int) -> bool:
    """滑动窗口（R10.3 统一版：vision/rag 各两窗共用实现，codebuddy 仍独立）。
    单线程事件循环下"清窗口→判满→追加"不会被切走，无需额外锁。"""
    now = time.time()
    while hits and now - hits[0] > window:
        hits.pop(0)
    if len(hits) >= cap:
        return False
    hits.append(now)
    return True


# ── R10.3（评审B 四-4①）/R10.4（评审B 🟡 三代化）：账本旋转——单代 .old 会被洪泛二次旋转覆盖
# =定向销毁证据链；改 .1/.2/.3 三代滚动。实际稳定态代链=.1/.2/.3/.4 四个后缀+活代=5 份×10MB=50MB/本
# （R10.4 收官轮 评审A/评审B 计数对账：多保一代=证据保留更久，无害偏差，注释按实记账。）
_ROTATE_BYTES = 10 * 1024 * 1024


def _rotate_log(p: Path) -> None:
    try:
        if p.exists() and p.stat().st_size > _ROTATE_BYTES:
            for i in (3, 2, 1):
                nxt = p.with_name(f"{p.name}.{i + 1}")
                cur = p.with_name(f"{p.name}.{i}")
                if cur.exists():
                    nxt.unlink(missing_ok=True)
                    cur.replace(nxt)
            p.replace(p.with_name(p.name + ".1"))
    except Exception:
        pass  # 旋转失败不影响记账（观测面）


def _token_audit(action: str, ok: bool, **extra) -> None:
    """R10.2（hy4 ②-2/②-3）：首设/清除/删码这类最高权动作必须有账——
    被抢注至少可追溯（时间+动作+结果+IP）。落 secrets 卷（被审计方摸不到）；写失败只出声。"""
    try:
        import datetime as _dt
        import json as _j
        rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "action": action, "ok": bool(ok)}
        rec.update({k: str(v)[:60] for k, v in extra.items()})
        log = _secrets_dir() / "token_audit.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log(log)
        with log.open("a", encoding="utf-8") as f:
            f.write(_j.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[token] 审计日志写入失败：{e}", flush=True)


def _presented_token(request) -> str:
    """凭证呈现顺序：显式头（Bearer/x-token）优先（CLI/助手进程内场景），HttpOnly Cookie 兜底（浏览器）。
    R10.5 XSS L2（OWASP 会话管理清单+LibreChat 模式）：管理员密钥种入 httponly+samesite=strict 的
    Cookie——浏览器里的恶意脚本物理上读不到它；localStorage 不再是新钥匙的存放地。"""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    xt = (request.headers.get("x-token") or "").strip()
    if xt:
        return xt
    try:
        return (request.cookies.get("m_admin_token") or "").strip()
    except Exception:
        return ""
