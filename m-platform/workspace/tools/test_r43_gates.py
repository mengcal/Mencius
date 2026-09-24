# -*- coding: utf-8 -*-
"""r43 回归：acceptance_kit（含 hy4 Q3 病例）+ _write_targets（含 hy4 Q2 六+二闸门）。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent.acceptance_kit import extract_literals, check_path_form, literal_diff  # noqa: E402
from mia_agent.flow_observer import _write_targets  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


def _pv(r):
    return [v for v, _ in r["paths"]]


def _qv(r):
    return [v for v, _ in r["quotes"]]


# ═══ 一、acceptance_kit（r42 原 15 项迁移 tuple 形） ═══
r = extract_literals(r"写 notes/report.md（覆盖旧内容），内容三行：第二行要包含一个 Windows "
                     r"反斜杠路径 D:\m\workspace，以及方括号尖括号和与号的字符集。")
T("W5 report.md 抓到", any("report.md" in p for p in _pv(r)))
T("W5 D:\\m\\workspace 抓到", any("workspace" in p for p in _pv(r)))
T("W5 不触发澄清", not r["needs_clarification"])
items = [{"kind": "path", "value": "D:\\m\\workspace"},
         {"kind": "path", "value": "notes/report.md"}]
artifact = 'notes/report.md\n"双引号"和\nD:\\workspace [正常] & 与号\n第三行中文'
miss = literal_diff(items, artifact)
T("W5 失真被逮", len(miss) == 1 and miss[0]["value"] == "D:\\m\\workspace")
r5 = extract_literals("统计 notes/ 根目录各 md 文件的行数，汇总成表写入 notes/stats.md。")
T("C5 stats.md 抓到", any("stats.md" in p for p in _pv(r5)))
r3 = extract_literals('在 notes/todo.md 追加一行"晚饭后检查 m-health"。')
T("引文抓到", "晚饭后检查 m-health" in _qv(r3))
T("todo.md 抓到", any("todo.md" in p for p in _pv(r3)))
T("无字面量写任务要澄清", extract_literals("帮我整理下笔记。")["needs_clarification"])
T("纯聊天不澄清", not extract_literals("今天天气怎么样")["needs_clarification"])
T("F1 读任务不澄清", not extract_literals("看看 notes/ 里有哪些文件，报个数就行。")["needs_clarification"])
rw = extract_literals("把 notes/工作规范.md 里某句改成另一句。")
T("W4 规范文件抓到", any("工作规范" in p for p in _pv(rw)))
T("Veda 炮：/notes/ 形态命中", check_path_form("ls -la /notes/") == ["/notes/"])
T("Veda 炮：相对不误报", check_path_form("find notes -maxdepth 1") == [])

# ═══ 二、hy4 Q3 病例：role 标注 ═══
h1 = extract_literals("把 README 里的「TODO」标记改成「已完成」")
qmap = dict(h1["quotes"])
T("hy4样例1: TODO 标 old-value", qmap.get("TODO") == "old-value")
T("hy4样例1: 已完成 标 target", qmap.get("已完成") == "target")
d1 = literal_diff([{"kind": "quote", "value": "TODO", "role": qmap["TODO"]},
                   {"kind": "quote", "value": "已完成", "role": qmap["已完成"]}],
                  "README 新内容：已完成")
T("hy4样例1: 正确产物全过（旧值已清+新值在场）", d1 == [])
d1b = literal_diff([{"kind": "quote", "value": "TODO", "role": "old-value"}], "还有 TODO 在")
T("hy4样例1: 旧值未清被逮", len(d1b) == 1)
h2 = extract_literals("不要动 notes/draft.md，只改 notes/final.md")
pmap = dict(h2["paths"])
T("hy4样例2: draft.md 标 forbidden", pmap.get("notes/draft.md") == "forbidden")
T("hy4样例2: final.md 保 target", pmap.get("notes/final.md") == "target")
h3 = extract_literals("把 timeout 从 30 改成 300")
T("hy4附带: 数字词界（30 假阴性封死）",
   literal_diff([{"kind": "number", "value": "30", "role": "old-value"},
                 {"kind": "number", "value": "300", "role": "target"}], "timeout=30") != [])

# ═══ 三、hy4 Q2 六闸门（必须全部非空/带标记）+ 二净闸门 ═══
DIRTY = ["rm -rf /etc/x", "echo x 1>/etc/a", "sed -i 's/a/b/' /etc/hosts",
         "OUT=/etc/cron.d/x; echo hi > $OUT", "tee >(cat > /etc/x) < /data/a",
         "mv /data/x /etc/y"]
for cmd in DIRTY:
    t = _write_targets(cmd)
    T(f"闸门非空: {cmd}", any(x.startswith("/etc") or x.startswith("unresolved") or x == "/etc/y"
                             or "/etc" in x for x in t) if cmd != "echo x 1>/etc/a" else "/etc/a" in t)
CLEAN = ["ls -la /notes 2>/dev/null || echo \"NOT_FOUND\"", "cmd 2>&1 | tee /data/mia_home/log"]
for cmd in CLEAN:
    from mia_agent.flow_observer import FlowObserver as _FO
    _flags = _FO.__new__(_FO)._scope_flags("execute", {"command": cmd})
    T(f"净闸门 flags 无越界: {cmd[:32]}", not any(str(x).startswith("out-of-scope") for x in _flags))
T("W2 原案 /notes 不误伤（重定向读命令无写落点）",
   "out-of-scope:/notes" not in str(_write_targets("ls -la /notes 2>/dev/null || echo x")))

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
