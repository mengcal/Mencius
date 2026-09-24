# -*- coding: utf-8 -*-
"""remember_rules "批准并记住这类"规则表回归测（09-15 盲区补测一期）。

四护栏的行为钉：①(tool,key) 精确匹配、②永不支持通配/全工具放行、
③绝对/相对双形态键归一（r49b）、④免卡判定=hit 为真。纯函数件，零 mock。
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from mia_agent.remember_rules import _norm_key, hit, rule_key  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


# ── rule_key：键规范化 ──
T("write_file 键=小写+去头斜杠", rule_key("write_file", {"file_path": "/Notes/Stats.md"})
  == "write_file:notes/stats.md")
T("绝对/相对双形态同键（r49b）",
  rule_key("edit_file", {"file_path": "/notes/stats.md"})
  == rule_key("edit_file", {"file_path": "notes/stats.md"}))
T("read_file 在名单", bool(rule_key("read_file", {"path": "a.md"})))
T("delete 系在名单", bool(rule_key("delete", {"file_path": "/x/y.md"}))
  and bool(rule_key("delete_file", {"path": "z.md"})))
T("execute 键=压缩空白+小写+截120",
  rule_key("execute", {"command": "  RM   -RF  A.txt\n b "})
  == "execute:rm -rf a.txt b")
T("execute 超长命令截 120",
  len(rule_key("execute", {"command": "x " * 200})) <= len("execute:") + 120)
T("名单外工具不可记（全工具放行=0）", rule_key("web_search", {"q": "any"}) == "")
T("start_async_task 类派活工具不可记", rule_key("start_async_task", {"task": "t"}) == "")
T("空参不可记", rule_key("write_file", {}) == "" and rule_key("write_file", None) == "")
T("file_path 缺失走 path 别名", _norm_key("write_file", {"path": "p.md"}) == "p.md")

# ── hit：精确匹配 ──
S = {"remember_rules": [{"key": "write_file:notes/stats.md"}]}
T("同 tool 同键命中（绝对形态调用）", hit("write_file", {"file_path": "/notes/stats.md"}, S))
T("同 tool 同键命中（相对形态调用）", hit("write_file", {"file_path": "notes/stats.md"}, S))
T("规则键大小写不敏感", hit("write_file", {"file_path": "notes/stats.md"},
                            {"remember_rules": [{"key": "WRITE_FILE:Notes/Stats.md"}]}))
T("跨 tool 不通配", not hit("edit_file", {"file_path": "/notes/stats.md"}, S))
T("前缀不算命中（精确等值）",
  not hit("write_file", {"file_path": "/notes/stats.md.bak"}, S))
T("execute 同键命中", hit("execute", {"command": "ls -la"},
                          {"remember_rules": [{"key": rule_key("execute", {"command": "LS   -LA"})}]}))

# ── 永不支持通配/空键规则 ──
W = {"remember_rules": [{"key": "write_file:*"}, {"key": "execute:*"},
                        {"key": "*"}, {"key": ""}]}
T("星号通配永不命中", not hit("write_file", {"file_path": "a.md"}, W))
T("execute 通配永不命中", not hit("execute", {"command": "echo hi"}, W))
T("空键规则永不误伤", not hit("read_file", {"path": "a.md"}, W))
T("不可记工具恒 False（即便 settings 满是规则）",
  not hit("web_search", {"q": "x"}, W) and not hit("dispatch_external", {"url": "u"}, W))

# ── 边界 settings 形态 ──
T("settings None 安全", not hit("write_file", {"file_path": "a.md"}, None))
T("无 remember_rules 键安全", not hit("write_file", {"file_path": "a.md"}, {}))
T("规则缺 key 字段不炸", not hit("write_file", {"file_path": "a.md"},
                                 {"remember_rules": [{"memo": "手滑"}]}))

# ── 免卡路径语义（护栏3/4 的判定面：命中=True=免卡放行；永久=无时效字段参与） ──
T("免卡=hit 真（无 TTL/次数变量参与判定）",
  hit("write_file", {"file_path": "/notes/stats.md"},
      {"remember_rules": [{"key": "write_file:notes/stats.md",
                           "note": "日常统计", "ts": 1}]}) is True)

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
