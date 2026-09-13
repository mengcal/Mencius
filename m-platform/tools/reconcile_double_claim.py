# -*- coding: utf-8 -*-
"""双领对账（NOVA 晨卷）：扫批准账找"同 tid 多条 external_claim"——
单岗单实例纪律破没破，账本说话（相邻秒双 claim=竞态双领证据）。
用法：容器内 python tools/reconcile_double_claim.py（宿主改 sys.path）。"""
import sys, json, collections
sys.path.insert(0, "/deps/outer-workspace/src")
import approvals as ap  # noqa: E402

claims = collections.defaultdict(list)
with open(ap._audit_path(), encoding="utf-8") as f:
    for ln in f:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("ev") == "external_claim":
            claims[(r.get("tid"), r.get("tool"))].append(r.get("ts", 0))

bad = []
for k, ts in claims.items():
    if len(ts) < 2:
        continue
    gap = sorted(ts)
    deltas = [round(b - a, 1) for a, b in zip(gap, gap[1:])]
    # 首跑分型教训（09-14 晨）：间隔>claim_timeout(1800s) 的双 claim=**超时重投**
    # （at-least-once 设计语义），不是竞态；竞态双领 signature=**秒级**相邻。
    if min(deltas) < 60:
        bad.append((k, ts, deltas))
    else:
        print(f"  · 重投型（非竞态）tid={k[0] or '<空=僵尸单史>'} post={k[1]} 间隔={deltas}")

print(f"claim 记录 {sum(len(v) for v in claims.values())} 条 / 涉及单 {len(claims)} 个")
if bad:
    for (tid, tool), ts, deltas in bad:
        print(f"  ⚠ 竞态双领嫌疑 tid={tid} post={tool} 次数={len(ts)} 间隔={deltas}")
    sys.exit(1)
print("OK：无秒级竞态双领（单岗单实例纪律未破；重投型已分型剔除）")
