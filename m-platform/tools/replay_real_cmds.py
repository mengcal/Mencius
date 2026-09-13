# -*- coding: utf-8 -*-
"""Lyra 预演件落地：从观测账 flow_obs 抽米娅真实 execute 命令，跑 guard 测误杀率。
口径：只看"当年弹过卡且爸爸批了"的日常动作=合法动作集；合法集里 mid/high 命中=误杀样本。"""
import sys, json, glob, collections
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent.guard_scan import scan_tool  # noqa: E402

cmds = []
for p in glob.glob("/deps/outer-workspace/src/mia_home/notes/flow_obs*.jsonl"):
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("tool") == "execute":
                    c = str(r.get("cmd") or "")  # r61b：观测账新字段（09-14 起有语料）
                    if c:
                        cmds.append(c)
    except FileNotFoundError:
        pass
# 去重保序取最近 200 条
seen, uniq = set(), []
for c in reversed(cmds):
    if c not in seen:
        seen.add(c); uniq.append(c)
uniq = uniq[:200]
stats = collections.Counter()
hits = []
for c in uniq:
    g = scan_tool("execute", {"command": c})
    stats[g["level"]] += 1
    if g["level"] != "low":
        hits.append((g["level"], c[:70], g["findings"][:1]))
print(f"样本 {len(uniq)} 条真实命令：", dict(stats))
print(f"误杀率（非 low 占比，这批全是日常合法动作）= "
      f"{(stats['mid'] + stats['high']) / max(1, len(uniq)):.1%}")
for lvl, c, f in hits[:15]:
    print(f"  [{lvl}] {f} :: {c}")
