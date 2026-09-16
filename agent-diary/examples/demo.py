# -*- coding: utf-8 -*-
"""
AgentDiary v0.4 完整演示

演示：
1. 初始化存储
2. 创建门禁（v0.2 六条军规版）
3. 读笔记/写日志
4. 门禁拦截演示
5. 审计仪表盘
6. 搜索功能（v0.4 升级）
"""

import sys
import os
# bug4修复：加sys.path引导，不用PYTHONPATH=.也能跑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_diary import DiaryStore, DiaryGate, make_diary_tools, AuditDashboard

# 1. 初始化存储（数据存在 ./diary_data/）
store = DiaryStore("./diary_data")

# 2. 创建门禁中间件（v0.2 六条军规版）
gate = DiaryGate(
    store=store,
    read_before_execute=True,   # 不读笔记不能动手
    write_after_task=True,      # 动完必须写日志
    fail_closed=True,           # 门禁出错时默认拒
)

# 3. 创建日记工具
read_diary, write_diary = make_diary_tools(store, gate)

# 4. 创建审计仪表盘（v0.3 新增）
dashboard = AuditDashboard(store)

# 模拟一个会话
session_id = "demo_session_001"

print("=" * 60)
print("AgentDiary v0.4 完整演示")
print("=" * 60)

# ── 场景1：不读笔记就想动手，被门禁拦住 ──
print("\n【场景1】不读笔记就想动手：")
allowed, result = gate.wrap_tool_call_sync(
    session_id, "run_command", "ls -la",
    handler=lambda req: f"执行: {req}"
)
print(f"  尝试调用 run_command...")
print(f"  门禁结果: {'放行' if allowed else '⛔ 拦截'}")
print(f"  返回: {str(result)[:100]}")

# ── 场景2：先读笔记 ──
print("\n【场景2】先读笔记：")
diary_content = read_diary(query="群发邮件", days=7)
print(f"  read_diary 结果（前200字）:")
print(f"  {diary_content[:200]}...")

# 标记已读
store.mark_read_diary(session_id)

# ── 场景3：读了笔记，门禁放行 ──
print("\n【场景3】读了笔记后再动手：")
allowed, result = gate.wrap_tool_call_sync(
    session_id, "run_command", "ls -la",
    handler=lambda req: f"✅ 执行成功: {req}"
)
print(f"  尝试调用 run_command...")
print(f"  门禁结果: {'✅ 放行' if allowed else '⛔ 拦截'}")
print(f"  返回: {result}")

# ── 场景4：任务完成，写日志 ──
print("\n【场景4】任务完成，写日志：")
result = write_diary(
    event="测试了AgentDiary v0.4",
    lesson="门禁拦截有效，搜索功能升级了",
    significance="important",
    context="完整演示",
    agent="lyra",
)
print(f"  {result}")

# ── 场景5：写了日志，任务算完成 ──
print("\n【场景5】写了日志后，任务完成检查：")
store.mark_written_diary(session_id)
allowed, reason = gate.check_task_completed(session_id)
print(f"  门禁结果: {'✅ 任务完成' if allowed else '⛔ 未完成'}")
print(f"  原因: {reason}")

# ── 场景6：审计仪表盘（v0.3 新增）──
print("\n【场景6】审计仪表盘：")
print(dashboard.report())

# ── 场景7：搜索功能（v0.4 新增）──
print("\n【场景7】搜索功能：")
results = store.search_semantic_facts("邮件 Cc")
print(f"  搜索'邮件 Cc'，找到 {len(results)} 条结果:")
for r in results:
    print(f"    - {r['title']}: {r['fact'][:40]}...")

print("\n" + "=" * 60)
print("演示完成！")
print("=" * 60)
