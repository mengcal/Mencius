# -*- coding: utf-8 -*-
"""AgentDiary 门禁钩子（gate_hook）九例回归测试（v1.2 纳仓版）。

跑法：python hooks/test_gate_hook.py
退出码 0 = 全过。

覆盖九类（对齐 hooks/README.md）：
 1. 未读日记：写类命令 deny（rm / git push）
 2. 读日记活路：python diary.py read 永远 allow
 3. sed 判定：sed -n 只读 allow / sed -i 写入 deny
 4. 复合命令按段判定：危险段 deny / 全只读 allow
 5. 引号路径读日记不误拦
 6. 前导环境变量赋值跳过
 7. git 安全子命令白名单
 8. 已读日记后写类命令放行
 9. GATE-OFF 急停：全放行
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "gate_hook.py"
PKG = Path(__file__).resolve().parent.parent  # agent-diary 仓根（含 agent_diary 包）
sys.path.insert(0, str(PKG))
from agent_diary.store import DiaryStore  # noqa: E402

FAIL = 0


def check(name, cond):
    global FAIL
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}")
    if not cond:
        FAIL += 1


def call_hook(base, sid, cmd, gate_off=False):
    """喂一条 Bash 命令给钩子，返回 permissionDecision。"""
    env = dict(os.environ, GATE_DIARY_ROOT=str(base), GATE_DIARY_PKG=str(PKG))
    if gate_off:
        (base / "GATE-OFF").write_text("")
    payload = json.dumps({
        "session_id": sid,
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
    })
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, capture_output=True, text=True, env=env,
    )
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
    except Exception:
        return f"PARSE_ERR: {r.stdout[:120]!r} {r.stderr[:120]!r}"


def main():
    tmp = tempfile.mkdtemp(prefix="gate_hook_test_")
    try:
        base = Path(tmp)
        store = DiaryStore(str(base))

        print("\n[1] 未读日记：写类命令必须 deny")
        check("rm -rf 未读→deny",
              call_hook(base, "s1", "rm -rf /tmp/xx") == "deny")
        check("git push 未读→deny",
              call_hook(base, "s1", "git push origin main") == "deny")

        print("\n[2] 读日记活路：永远 allow")
        check("python diary.py read→allow",
              call_hook(base, "s2", "python diary.py read") == "allow")
        check("python3 diary.py read 关键词→allow",
              call_hook(base, "s2", "python3 diary.py read 键盘") == "allow")

        print("\n[3] sed 只读/写入判定")
        check("sed -n 只读→allow",
              call_hook(base, "s3", "sed -n '1p' /etc/hostname") == "allow")
        check("sed -i 写入→deny",
              call_hook(base, "s3", "sed -i 's/a/b/' /tmp/f") == "deny")

        print("\n[4] 复合命令按段判定")
        check("echo && rm 危险段→deny",
              call_hook(base, "s4", "echo ok && rm /tmp/x") == "deny")
        check("echo && cat 全只读→allow",
              call_hook(base, "s4", "echo hi && cat /etc/hostname") == "allow")

        print("\n[5] 引号路径读日记不误拦")
        check('python "/tmp/my dir/diary.py" read→allow',
              call_hook(base, "s5", 'python "/tmp/my dir/diary.py" read') == "allow")

        print("\n[6] 前导环境变量赋值跳过")
        check("FOO=bar python3 diary.py read→allow",
              call_hook(base, "s6", "FOO=bar python3 diary.py read") == "allow")

        print("\n[7] git 安全子命令白名单")
        check("git status→allow",
              call_hook(base, "s7", "git status") == "allow")
        check("git log→allow",
              call_hook(base, "s7", "git log --oneline -3") == "allow")

        print("\n[8] 已读日记后：写类命令放行")
        store.mark_read_diary("s8")
        check("已读后 rm→allow",
              call_hook(base, "s8", "rm -rf /tmp/xx") == "allow")

        print("\n[9] GATE-OFF 急停：全放行")
        check("GATE-OFF 后 rm→allow",
              call_hook(base, "s9", "rm -rf /", gate_off=True) == "allow")

        print(f"\n{'=' * 40}")
        if FAIL:
            print(f"❌ {FAIL} 项失败")
            sys.exit(1)
        print("✅ gate_hook 九例回归全过！")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
