#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mia_cli.py — M 平台命令行入口（爸 09-30 令：知夏↔米娅直连，不绕信箱）。

用法:
  python mia_cli.py send "消息"    # 发给米娅（固定线程=上下文连续），等回复打印
  python mia_cli.py new            # 开新线程（旧线程自然归档）
  python mia_cli.py last           # 读上次回复

鉴权: 密码从 D:/glm/secrets/m_cli_auth.txt 首行读（无则交互输入一次并保存）→
      POST /auth/login 换管理员 token（与浏览器同一正门，R10.408 注册制）。
目标: 只允许固定本机平台 origin（127.0.0.1:2024，爸爸本机自持 M 平台）——
      _url() 对每个最终 URL 做 origin 白名单校验 + 3xx 不跟随，双闸。
"""
import json
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


def _req(path, token=None, data=None, timeout=300):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(_url(path), data=body, headers=headers,
                                 method="POST" if body is not None else "GET")
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=timeout) as r:
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
    tok = d.get("token") or d.get("access_token") or ""
    if not tok:
        sys.exit("登录失败: " + json.dumps(d, ensure_ascii=False)[:200])
    TOKEN_CACHE.write_text(tok, encoding="utf-8")
    return tok


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
    """发一条并打印米娅的回复（send 命令与交互模式共用）。"""
    tid = get_thread(token)
    state = _req("/threads/" + tid + "/runs/wait", token,
                 data={"assistant_id": ASSISTANT,
                       "input": {"messages": [{"role": "user", "content": msg}]}},
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
                TOKEN_CACHE.unlink()  # token 失效：清缓存重登一次（自愈，不烦人）
                token = login()
                try:
                    send_once(token, line)
                except Exception as e2:
                    print("发送失败:", type(e2).__name__, str(e2)[:200])
            else:
                print("发送失败:", type(e).__name__, str(e)[:200])
        except Exception as e:
            print("发送失败:", type(e).__name__, str(e)[:200])


def main():
    argv = sys.argv[1:]
    if not argv:
        chat_mode()  # 无参数=直接进入对话（爸要的"进入界面就自然语言交流"）
        return
    cmd = argv[0].lower()
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
                token = login()
                send_once(token, " ".join(argv[1:]))
            else:
                print("发送失败:", type(e).__name__, str(e)[:200])
    elif cmd == "last":
        print(LAST_FILE.read_text(encoding="utf-8") if LAST_FILE.exists() else "(还没有记录)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
