# -*- coding: utf-8 -*-
"""lark_bridge.py —— M 平台 × 飞书长连接桥 v2（09-19 知夏；v1 经 ds-v4.1-flash 挑刺 22 条后重写）

链路：爸爸飞书发消息 → 飞书长连接推给本桥 → 线程池调 M 平台 agent 图 → 米娅回复推回飞书。
安全（v2 按 ds 复测收敛）：
- 白名单强制：LARK_BRIDGE_ALLOW 必须非空才允许启动（fail-closed，#1/#2）；
- 只响应 p2p 单聊（#7 群聊公开回复风险）；
- message_id 去重（#5 飞书超时重推）+ Semaphore(2) 并发闸（#6）；
- call_mia 丢线程池立刻 ACK（#4 阻塞心跳会被飞书判死）；
- API 回复用独立 lark.Client（#3 ws Client 无 .im 命名空间的防御性修复）。
配置（D:\\m\\.env）：LARK_BRIDGE_APP_ID / LARK_BRIDGE_APP_SECRET / LARK_BRIDGE_ALLOW（openId 逗号分隔）。
自检：python lark_bridge.py --check。
"""
import json
import os
import re
import sys
import threading

import httpx

OFFICE = os.environ.get("MIA_OFFICE_URL", "http://127.0.0.1:2024")
GRAPH = os.environ.get("MIA_LARK_GRAPH", "agent")
APP_ID = os.environ.get("LARK_BRIDGE_APP_ID", "")
APP_SECRET = os.environ.get("LARK_BRIDGE_APP_SECRET", "")
ALLOW = [s.strip() for s in os.environ.get("LARK_BRIDGE_ALLOW", "").split(",") if s.strip()]
SECRETS = os.environ.get("MIA_SECRETS_PATH", r"D:\m\secrets\.settings_secrets")
HOSTCOPY = os.environ.get("MIA_HOSTCOPY_TOKEN", r"D:\m\guard\hostcopy.token")
MAX_INPUT = 2000   # 入站文本上限（#12 token 爆炸面）
MAX_REPLY = 3800
_SEM = threading.Semaphore(2)     # 并发闸（#6）
_SEEN = set()                     # message_id 去重（#5）
_SEEN_LOCK = threading.Lock()
_api_client = None                # 独立 API client（#3）


def admin_token() -> str:
    """平台管理员令牌：env → 守卫明文副本 → .settings_secrets（legacy）。"""
    v = os.environ.get("MIA_OFFICE_TOKEN", "")
    if v:
        return v
    try:
        t = open(HOSTCOPY, encoding="utf-8").read().strip()
        if t:
            return t
    except OSError:
        pass
    try:
        with open(SECRETS, encoding="utf-8") as f:
            m = re.search(r'general\.apiToken"?\s*[:=]\s*"([a-f0-9]{16,})"', f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def _thread_for(chat_id: str) -> str:
    """取/建该飞书会话绑定的平台线程（v2.2 会话连续）。tid 过 UUID 白名单后才入 body（Mimosa 加固：不做动态 URL）。"""
    tok = admin_token()
    with _THREADS_LOCK:
        tid = _THREADS.get(chat_id, "")
    if tid:
        return tid
    try:
        r = httpx.post(f"{OFFICE}/threads", json={}, headers={"x-api-key": tok}, timeout=30)
        tid = (r.json() or {}).get("thread_id", "") or ""
    except Exception:
        tid = ""
    if tid and not re.fullmatch(r"[0-9a-fA-F-]{16,64}", tid):
        print("[桥] thread_id 格式异常，弃用会话连续", flush=True)
        tid = ""
    if tid:
        with _THREADS_LOCK:
            _THREADS[chat_id] = tid
    return tid


def call_mia(text: str, chat_id: str = "") -> str:
    """跑一轮 agent 图：有 chat_id 则 thread_id 走请求体（会话连续），否则一次性无线程。
    URL 恒定 f"{OFFICE}/runs/wait"——零动态路径（Mimosa SSRF 加固：tid 只进 body 且过 UUID 白名单）。"""
    tok = admin_token()
    if not tok:
        return "[桥错误] 平台令牌读取失败"
    body = {"assistant_id": GRAPH, "input": {"messages": [{"role": "user", "content": text}]}}
    if chat_id:
        tid = _thread_for(chat_id)
        if tid:
            body["thread_id"] = tid  # thread_id 走 body，URL 恒定
    try:
        r = httpx.post(f"{OFFICE}/runs/wait", json=body,
                       headers={"x-api-key": tok}, timeout=300)
    except Exception as e:
        return f"[桥错误] 平台不可达: {str(e)[:120]}"
    if r.status_code != 200:
        return f"[平台 {r.status_code}] {r.text[:200]}"
    try:
        msgs = (r.json() or {}).get("messages") or []
    except ValueError:  # #9 非 JSON 回体
        return "[平台返回非 JSON]"
    for m in reversed(msgs):
        mtype = m.get("type") if isinstance(m, dict) else getattr(m, "type", None)
        if mtype == "ai":
            c = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if isinstance(c, list):
                c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
            return (c or "[空回复]") if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
    return "[平台返回无 AI 消息]"


def _reply(message_id: str, text: str) -> None:
    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
    req = (ReplyMessageRequest.builder()
           .message_id(message_id)
           .request_body(ReplyMessageRequestBody.builder()
                         .content(json.dumps({"text": text[:MAX_REPLY]}, ensure_ascii=False))
                         .msg_type("text").build()).build())
    resp = _api_client.im.v1.message.reply(req)
    if not resp.success():
        print(f"[桥] 回复失败: {resp.code} {resp.msg}", flush=True)


def on_message(data) -> None:
    """飞书事件入口：快速 ACK（重活丢线程），所有异常不杀长连接。"""
    try:
        ev = data.event
        mid = ev.message.message_id
        with _SEEN_LOCK:
            if mid in _SEEN:
                return  # #5 去重
            _SEEN[mid] = True
            if len(_SEEN) > 500:
                for k in list(_SEEN)[:250]:  # ds v2 复测：清半留半，防批量重推全部复活
                    _SEEN.pop(k, None)
        sender = (ev.sender.sender_id.open_id if ev.sender and ev.sender.sender_id else "") or ""
        if sender not in ALLOW:  # #1 白名单强制（含空=拒所有）
            print(f"[桥] 白名单外拒绝: {sender[:12]}...", flush=True)
            return
        if ev.message.chat_type != "p2p":  # #7 只服务单聊
            print("[桥] 群聊消息忽略", flush=True)
            return
        content = json.loads(ev.message.content or "{}")
        text = re.sub(r"@_user_\d+", "", (content.get("text") or "")).strip()  # #11 @ 占位符
        if not text:
            return
        text = text[:MAX_INPUT]
        print(f"[桥] {sender[:12]}...: {text[:60]}", flush=True)
        if not _SEM.acquire(blocking=False):
            threading.Thread(target=_reply, args=(mid, "[桥] 上一单还在跑（并发 2），稍后再发"),
                             daemon=True).start()  # ds v2 复测：占满路径的回复也不许进事件线程
            return
        def work():
            try:
                _reply(mid, call_mia(text, chat_id=ev.message.chat_id))
            except Exception as e:
                print(f"[桥] 工作线程异常: {str(e)[:200]}", flush=True)
            finally:
                _SEM.release()
        threading.Thread(target=work, daemon=True).start()  # #4 立刻 ACK
    except Exception as e:
        print(f"[桥] 事件异常: {str(e)[:200]}", flush=True)


def do_check() -> int:
    ok = True
    for name, v in [("LARK_BRIDGE_APP_ID", APP_ID), ("LARK_BRIDGE_APP_SECRET", APP_SECRET)]:
        good = bool(v)
        ok = ok and good
        print(f"{'✓' if good else '✗'} {name}{'已配置' if good else '未配置（.env 补键）'}")
    good = bool(ALLOW)
    ok = ok and good
    print(f"{'✓' if good else '✗'} LARK_BRIDGE_ALLOW 白名单{'=' + ','.join(a[:10] + '...' for a in ALLOW) if good else '为空（v2：拒绝启动）'}")
    tok = admin_token()
    good = bool(tok)
    ok = ok and good
    print(f"{'✓' if good else '✗'} 平台管理员令牌{'读取成功' if good else '读取失败'}")
    try:
        r = httpx.get(f"{OFFICE}/health", timeout=10)
        good = r.status_code == 200
        print(f"{'✓' if good else '✗'} 平台 {OFFICE} → HTTP {r.status_code}")
    except Exception as e:
        good = False
        print(f"✗ 平台不可达: {str(e)[:120]}")
    ok = ok and good
    if tok:
        try:
            r = httpx.post(f"{OFFICE}/runs/wait", json={"assistant_id": GRAPH,
                           "input": {"messages": [{"role": "user", "content": "只回复两个字：在线"}]}},
                           headers={"x-api-key": tok}, timeout=300)
            msgs = []
            if r.status_code == 200:
                try:
                    msgs = (r.json() or {}).get("messages") or []  # #8/#9
                except ValueError:
                    msgs = []
            tail = str(msgs[-1].get("content", ""))[:40] if msgs else r.text[:60]
            good = r.status_code == 200 and bool(msgs)
            print(f"{'✓' if good else '✗'} agent 图试跑 → HTTP {r.status_code} | 尾回复: {tail}")
        except Exception as e:
            good = False
            print(f"✗ agent 图试跑异常: {str(e)[:120]}")
        ok = ok and good
    print("自检结论:", "全部通过，只差飞书应用凭证即可上线" if ok else "有未过项，按 ✗ 逐条补")
    return 0 if ok else 1


def main() -> int:
    global _api_client
    if "--check" in sys.argv:
        return do_check()
    if not (APP_ID and APP_SECRET):
        raise SystemExit("LARK_BRIDGE_APP_ID / LARK_BRIDGE_APP_SECRET 未配置")
    if not ALLOW:  # #2 白名单强制为启动前置
        raise SystemExit("LARK_BRIDGE_ALLOW 为空——v2 拒绝裸奔启动（fail-closed）")
    import lark_oapi as lark
    _api_client = (lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build())  # #3 独立 API client
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_message).build())
    ws = lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO)
    print(f"[桥] 长连接启动（graph={GRAPH} 白名单={len(ALLOW)} p2p-only）", flush=True)
    ws.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
