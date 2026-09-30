#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mia_cli.py — M 平台命令行入口（爸 09-30 令：知夏↔米娅直连，不绕信箱）。

用法:
  python mia_cli.py send "消息"    # 发给米娅（固定线程=上下文连续），等回复打印
  python mia_cli.py new            # 开新线程（旧线程自然归档）
  python mia_cli.py last           # 读上次回复
  python mia_cli.py                # 无参数=交互对话模式（进界面直接聊，exit 退出）

鉴权: 凭据走 Cookie 罐持久化（D:/glm/secrets/m_cli_cookie.txt）——/auth/login 一次
      （密码从 m_cli_auth.txt 或交互输入），之后冷启动直接用罐内 Cookie，长期免登录。
      401 时不自动重登（每次 login=guard rotate 作废旧钥=会挤掉浏览器在线的爸爸）。
目标: 只允许固定本机平台 origin（127.0.0.1:2024，爸爸本机自持 M 平台）——
      _url() 对每个最终 URL 做 origin 白名单校验 + 3xx 不跟随，双闸。
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ALLOWED_ORIGIN = "http://127.0.0.1:2024"  # 唯一合法目标：本机 M 平台（常量）
AUTH = pathlib.Path("D:/glm/secrets/m_cli_auth.txt")
TOKEN_CACHE = pathlib.Path("D:/glm/secrets/m_cli_token.txt")  # 登录一次长期缓存（CB/qodercn 同款姿势）
THREAD_FILE = pathlib.Path("D:/glm/projects/celia-work/mia-cli-thread.txt")
LAST_FILE = pathlib.Path("D:/glm/projects/celia-work/mia-cli-last.json")
ASSISTANT = "agent"


def _url(path):
    """拼 URL 并做 origin 白名单校验——path 含线程 id 等动态段，最终必须仍锁在本机平台。"""
    full = ALLOWED_ORIGIN + path
    parts = urlsplit(full)
    if (parts.scheme + "://" + parts.netloc) != ALLOWED_ORIGIN or parts.scheme != "http":
        sys.exit("内部守卫：目标越界 " + full[:80])
    return full


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 3xx 一律不跟（防重定向出域）


# Cookie 罐：/auth/login 种一次，落盘持久化——后续进程启动 load，长期免登录（CB/qodercn 姿势）
_JAR_PATH = pathlib.Path("D:/glm/secrets/m_cli_cookie.txt")
_JAR = __import__("http.cookiejar", fromlist=["MozillaCookieJar"]).MozillaCookieJar(str(_JAR_PATH))
try:
    if _JAR_PATH.exists():
        _JAR.load(ignore_discard=True, ignore_expires=True)
except Exception:
    pass  # 罐坏=当作未登录，下次 login 重建
_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(_JAR))


def _req(path, token=None, data=None, timeout=300):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    # 凭据走 Cookie 罐（/auth/login 种入）；cookie-session 假 Bearer 不发——
    # 发了守卫会优先验 Bearer 而忽略合法 Cookie（12:5x 实测 401 的根因）。
    if token and token != "cookie-session":
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(_url(path), data=body, headers=headers,
                                 method="POST" if body is not None else "GET")
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def login():
    # 姿势对齐 CB/qodercn：token 缓存优先（登录一次长期有效），只在失效时才用密码重登。
    # 密码文件=行1登录名/行2密码（仅兜底；平时不读）。
    if TOKEN_CACHE.exists():
        tok = TOKEN_CACHE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    name = pw = ""
    if AUTH.exists():
        lines = AUTH.read_text(encoding="utf-8").splitlines()
        name = (lines[0] if len(lines) > 0 else "").strip()
        pw = (lines[1] if len(lines) > 1 else "").strip()
    if not (name and pw):
        name = input("M 平台登录名: ").strip()
        pw = input("M 平台密码（缓存后长期有效，本机凭据区不进 git/笔记）: ").strip()
        AUTH.write_text(name + "\n" + pw, encoding="utf-8")
    d = _req("/auth/login", data={"username": name, "password": pw}, timeout=15)
    if d.get("ok") is not True:
        sys.exit("登录失败: " + json.dumps(d, ensure_ascii=False)[:200])
    _JAR.save(ignore_discard=True, ignore_expires=True)  # 罐落盘：后续进程免登录
    # r39q（爸被挤下线案）：cookie 值=guard token 同源，缓存之——后续冷启动直接
    # Bearer 使用，**不再触发 /auth/login**（每次 login=guard rotate 作废旧钥=挤掉
    # 浏览器在线的爸爸，useTaskAnnouncer 401 即此）。
    for ck in _JAR:
        TOKEN_CACHE.write_text(ck.value, encoding="utf-8")
        break
    return TOKEN_CACHE.read_text(encoding="utf-8").strip()


def get_thread(token, fresh=False):
    if not fresh and THREAD_FILE.exists():
        tid = THREAD_FILE.read_text(encoding="utf-8").strip()
        if tid:
            return tid
    t = _req("/threads", token, data={})
    tid = t.get("thread_id", "")
    THREAD_FILE.write_text(tid, encoding="utf-8")
    return tid


def extract_reply(state):
    msgs = state.get("values", {}).get("messages") or state.get("messages") or []
    for m in reversed(msgs):
        if (m.get("role") or m.get("type")) in ("assistant", "ai"):
            c = m.get("content") or ""
            if isinstance(c, list):
                c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
            if c.strip():
                return c
    return "(米娅本轮没有文本回复)"


def send_once(token, msg):
    """发一条并打印米娅的回复（send 命令与交互模式共用）。
    r39z：workspace 随 run 走官方 configurable 通道（对齐前端 page.tsx 同一条政令
    r36k）——环境变量 MIA_CLI_WS 选域，缺省 container 与前端默认一致；
    宿主域（MIA_CLI_WS=host）经 host_runner 落宿主 Git Bash，档位门照过不误。"""
    tid = get_thread(token)
    ws = (os.environ.get("MIA_CLI_WS") or "container").strip() or "container"
    state = _req("/threads/" + tid + "/runs/wait", token,
                 data={"assistant_id": ASSISTANT,
                       "input": {"messages": [{"role": "user", "content": msg}]},
                       "config": {"configurable": {"workspace": ws}}},
                 timeout=600)
    reply = extract_reply(state)
    print(reply, flush=True)
    LAST_FILE.write_text(json.dumps({"thread": tid, "reply": reply}, ensure_ascii=False),
                         encoding="utf-8")


def chat_mode():
    """交互模式：直接进入自然语言对话，exit/quit 退出（爸 09-30 令：不要每次敲 send）。"""
    token = login()
    tid = get_thread(token)
    print(f"已连接米娅（线程 {tid[:8]}…）——直接说话，exit 退出。")
    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.lower() in ("exit", "quit", "退出"):
            return
        try:
            send_once(token, line)
        except urllib.error.HTTPError as e:
            if e.code == 401 and TOKEN_CACHE.exists():
                TOKEN_CACHE.unlink()  # 缓存失效：不再自动 login（login=guard rotate=挤掉爸浏览器）
                print("token 已失效且已清缓存——为不挤掉爸爸浏览器的登录态，"
                      "mia_cli 不再自动登录。请在浏览器 F12 复制 mia_admin_token 存入 "
                      "D:/glm/secrets/m_cli_token.txt，或删除 m_cli_auth.txt 后重跑以密码登录（会触发 rotate）。")
            else:
                print("发送失败:", type(e).__name__, str(e)[:200])
        except Exception as e:
            print("发送失败:", type(e).__name__, str(e)[:200])


def take_orders():
    """取 celia-post 待办单（r39p 双向通道取单侧——米娅 dispatch_external 落的活）。
    领取=external_claim（条件化原子领取），干活后 external_store 回传。"""
    sys.path.insert(0, r"D:\m\workspace")
    import approvals as _ap
    rows = _ap.external_pending_view("celia-post", limit=5)
    if not rows:
        print("celia-post 暂无待办单。")
        return
    for r in rows:
        did = r.get("id", "")
        task = str(r.get("task", ""))[:200]
        claim = _ap.external_claim("celia-post", did)
        print(f"== 单 {did}（{'已领取' if claim else '领取失败/被抢'}）==")
        print(f"任务：{task}")
        print()


def main():
    argv = sys.argv[1:]
    if not argv:
        chat_mode()  # 无参数=直接进入对话（爸要的"进入界面就自然语言交流"）
        return
    cmd = argv[0].lower()
    if cmd == "orders":
        take_orders()
        return
    if cmd not in ("send", "new", "last"):
        print(__doc__)
        return
    token = login()
    if cmd == "new":
        print("新线程:", get_thread(token, fresh=True))
    elif cmd == "send" and len(argv) > 1:
        try:
            send_once(token, " ".join(argv[1:]))
        except urllib.error.HTTPError as e:
            if e.code == 401 and TOKEN_CACHE.exists():
                TOKEN_CACHE.unlink()
                print("token 已失效且已清缓存——不自动登录（防 rotate 挤掉爸爸浏览器）。"
                      "请重新提供 token 或删除 m_cli_auth.txt 后密码登录。")
            else:
                print("发送失败:", type(e).__name__, str(e)[:200])
    elif cmd == "last":
        print(LAST_FILE.read_text(encoding="utf-8") if LAST_FILE.exists() else "(还没有记录)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
