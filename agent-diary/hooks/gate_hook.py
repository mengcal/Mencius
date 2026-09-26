# -*- coding: utf-8 -*-
"""AgentDiary 门禁钩子 v1.2（宿主 PreToolUse 侧，仓库版）。

协议：stdin 收 PreToolUse JSON，stdout 回 permissionDecision（allow/deny）。
规则：执行类动作前，本会话必须先 read_diary；否则 deny 并 log_block。
防呆：钩子自身崩溃=非阻塞错误，不会锁死宿主；急停：数据根放 GATE-OFF 文件即全放行。

v1.2 纳仓版（09-25，西莉亚）：
- 路径参数化：数据根 GATE_DIARY_ROOT（默认 ~/.agent-diary/live），
  包路径 GATE_DIARY_PKG（agent_diary 包所在目录，默认=本仓根 hooks/..，按 hook 位置自动推导）；
  去除任何个人机器路径。
- v1.1 修复全保留：shlex 分词（引号/绝对路径的 `python …diary.py read` 不误拦）、
  复合命令按段判定（&&/||/;/| 每段安全才放行）、前导环境变量赋值跳过、
  sed 仅 -n 只读放行（-i 拦）、git 仅 status/log/diff/show/branch 放行。

## 安装（ZCode 宿主）
1. 本文件随 agent-diary 仓分发；宿主把它复制/链接到 hooks 目录，
   并在 hook 配置中注册为 PreToolUse（命令：python <此文件路径>）。
2. 环境变量（可选）：GATE_DIARY_ROOT=日记数据根；GATE_DIARY_PKG=agent_diary 包所在目录。
3. 急停：在 GATE_DIARY_ROOT 下新建 GATE-OFF 空文件即全放行。

## 回归（九例对照）
见 m-platform 侧 celia-work/gate_hook_v11_test.py 同款用例：未读日记的写类命令 deny、
读日记命令 allow、sed -n allow / sed -i deny、复合命令分段、引号路径、前导 env 赋值。
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

BASE = Path(os.environ.get("GATE_DIARY_ROOT", str(Path.home() / ".agent-diary" / "live")))
_HOOK_SELF = Path(__file__).resolve()
# GATE_DIARY_PKG = agent_diary 包所在目录（含 agent_diary 子目录）；默认 = 本仓根（hooks/..）
DIARY_PKG = Path(os.environ.get(
    "GATE_DIARY_PKG",
    str(_HOOK_SELF.resolve().parent.parent),
))

SAFE_FIRST = {
    "ls", "cat", "head", "tail", "wc", "grep", "rg", "fd", "find", "date",
    "echo", "pwd", "which", "stat", "du", "df", "cd", "python", "python3",
}
GIT_SAFE = {"status", "log", "diff", "show", "branch"}
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _seg_safe(toks):
    """一个命令段的 token 列表是否只读安全。"""
    while toks and ENV_ASSIGN.match(toks[0]):
        toks = toks[1:]                        # 跳过 FOO=bar 前导赋值
    if not toks:
        return True
    head = os.path.basename(toks[0]).lower()
    if head == "git":
        return len(toks) > 1 and toks[1] in GIT_SAFE
    if head == "sed":
        args = toks[1:]
        # 只读姿势才放行：必须带 -n、不得带 -i（sed -i 是写文件，原白名单口径 "sed -n"）
        has_n = any(a == "-n" or (a.startswith("-") and not a.startswith("--") and "n" in a) for a in args)
        has_i = any(a == "-i" or (a.startswith("-") and not a.startswith("--") and "i" in a) for a in args)
        return has_n and not has_i
    if head.startswith("python"):
        # python [路径/]diary.py read … → 读日记活路永远敞开；其余 python 视为执行类
        return (len(toks) >= 3
                and os.path.basename(toks[1]).lower() == "diary.py"
                and toks[2].lower() == "read")
    return head in SAFE_FIRST and head not in ("python", "python3")


def safe_bash(cmd):
    try:
        segs = re.split(r"&&|\|\||;|\|", cmd)
    except Exception:
        return False
    for seg in segs:
        try:
            toks = shlex.split(seg.strip())
        except ValueError:
            toks = seg.split()
        if not _seg_safe(toks):
            return False
    return True


def emit(decision, reason=""):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }, ensure_ascii=False))
    sys.exit(0)


def main():
    data = json.load(sys.stdin)
    sid = data.get("session_id", "default")
    tool = data.get("tool_name", "")
    cmd = ""
    if tool == "Bash":
        cmd = (data.get("tool_input") or {}).get("command") or ""

    # 记录当前会话号，供 diary.py 对齐 session
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        (BASE / ".current-session").write_text(sid, encoding="utf-8")
    except OSError:
        pass

    if (BASE / "GATE-OFF").exists():
        emit("allow", "")

    # Bash 只读白名单放行（防死锁：读日记这条活路永远敞着）
    if tool == "Bash" and safe_bash(cmd):
        emit("allow", "")

    sys.path.insert(0, str(DIARY_PKG))
    from agent_diary.store import DiaryStore
    store = DiaryStore(str(BASE))
    if store.has_read_diary(sid):
        emit("allow", "")

    store.log_block(sid, tool, "read_not_done")
    emit("deny",
         "【日记门禁】动手前必读日记：跑 `python diary.py read 关键词`"
         "（session=" + str(sid) + "），读完再重试本操作。")


if __name__ == "__main__":
    main()
