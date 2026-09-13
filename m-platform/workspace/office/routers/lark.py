"""office.routers.lark —— 飞书桥（平台侧，r41 武装米娅第一批）

架构（NOVA 落位表 + Eve 五门）：
- 凭据：workspace/secrets/lark_app.txt（平台进程独读；不在沙箱挂载面、不进对话、不进日志）。
- 形态：米娅工具 lark_send 进程内直调本模块函数（同源先例：CodeBuddy 代理层窄接口）；
  对外 HTTP 面 /lark/* 进 _TOKEN_GUARDED（管理端/调试用）。
- 红线：tenant_access_token 只在内存缓存；日志只记目的与长度，正文不落。
- 外发批准门：在工具层（_NEEDS_EXTERNAL 含 lark_send），桥本身不弹卡——卡由 C1 管。
"""
from __future__ import annotations

import re
import time

import httpx
from fastapi import APIRouter, Body

from ..core import BASE, _token_audit

router = APIRouter()

_CRED_FILE = BASE / "secrets" / "lark_app.txt"
_API = "https://open.feishu.cn/open-apis"
_tok_cache: dict = {"token": "", "exp": 0.0}


def _cred() -> tuple[str, str]:
    t = _CRED_FILE.read_text(encoding="utf-8", errors="replace")
    app = re.search(r"(cli_[0-9a-f]+)", t)
    sec = re.search(r"(?i)secret\s*[=:：]\s*(\S+)", t)
    if not app or not sec:
        raise RuntimeError("lark_app.txt 格式不含 App ID(cli_…)/Secret——请爸爸检查")
    return app.group(1), sec.group(1)


def tenant_token() -> str:
    """tenant_access_token（应用身份），90 分钟缓存（官方 2h 有效）。"""
    now = time.time()
    if _tok_cache["token"] and now < _tok_cache["exp"]:
        return _tok_cache["token"]
    app_id, app_secret = _cred()
    r = httpx.post(f"{_API}/auth/v3/tenant_access_token/internal",
                   json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"飞书取 token 失败 code={j.get('code')} msg={j.get('msg')}"
                           "（检查：应用是否已创建版本并发布/权限是否开通/凭证是否正确）")
    _tok_cache.update(token=j["tenant_access_token"], exp=now + 5400)
    return j["tenant_access_token"]


def send_text(text: str, receive_id: str = "", id_type: str = "open_id") -> dict:
    """发文本消息。receive_id 空=默认发给爸爸（需先配置 dad_open_id，见 settings lark 节）。"""
    if not receive_id:
        try:
            from settings_mgr import load_settings
            receive_id = str((load_settings().get("lark", {}) or {}).get("dad_open_id", ""))
        except Exception:
            receive_id = ""
    if not receive_id:
        return {"ok": False, "error": "未配置收件人（settings.lark.dad_open_id 或显式 receive_id）"}
    r = httpx.post(
        f"{_API}/im/v1/messages?receive_id_type={id_type}",
        headers={"Authorization": f"Bearer {tenant_token()}"},
        json={"receive_id": receive_id, "msg_type": "text",
              "content": f'{{"text": {__import__("json").dumps(text, ensure_ascii=False)}}}'},
        timeout=15)
    j = r.json()
    ok = j.get("code") == 0
    # 审计脱敏：只记目的前 8 位与文本长度，正文不落日志（NOVA 四零接触区之日志面）
    _token_audit("lark_send", ok, to=receive_id[:8], length=len(text),
                 msg_id=(j.get("data") or {}).get("message_id", "")[:12] if ok else "",
                 err="" if ok else f"code={j.get('code')}")
    return {"ok": ok, "error": "" if ok else f"code={j.get('code')} msg={j.get('msg')}"}


@router.post("/lark/ping")
async def api_ping():
    """凭据与发布状态自检（不回显 token）。"""
    try:
        tenant_token()
        return {"ok": True, "who": "Mia-app tenant token 有效"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/lark/send")
async def api_send(req: dict = Body(...)):
    return send_text(str(req.get("text", "")), str(req.get("receive_id", "")),
                     str(req.get("id_type", "open_id")))
