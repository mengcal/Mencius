# -*- coding: utf-8 -*-
"""
AgentDiary 使用示例

演示：
1. 初始化存储
2. 创建门禁
3. 读笔记/写日志
4. 门禁拦截演示
"""

from agent_diary import DiaryStore, MemoryGate, make_diary_tools

# 1. 初始化存储（数据存在 ./diary_data/）
store = DiaryStore("./diary_data")

# 2. 创建门禁中间件
gate = MemoryGate(
    store=store,
    read_before_execute=True,   # 不读笔记不能动手
    write_after_task=True,      # 动完必须写日志
)

# 3. 创建日记工具
read_diary, write_diary = make_diary_tools(store, gate)

# 模拟一个会话
session_id = "demo_session_001"

print("=" * 60)
print("AgentDiary 演示")
print("=" * 60)

# ── 场景1：不读笔记就想动手，被门禁拦住 ──
print("\n【场景1】不读笔记就想动手：")
allowed, reason = gate.check_read_before(session_id, "run_command")
print(f"  尝试调用 run_command...")
print(f"  门禁结果: {'放行' if allowed else '⛔ 拦截'}")
print(f"  原因: {reason}")

# ── 场景2：先读笔记 ──
print("\n【场景2】先读笔记：")
diary_content = read_diary(query="群发邮件", days=7)
gate.mark_task_started(session_id)
print(f"  read_diary 结果:")
print(diary_content[:200] + "..." if len(diary_content) > 200 else diary_content)

# ── 场景3：读了笔记，门禁放行 ──
print("\n【场景3】读了笔记后再动手：")
allowed, reason = gate.check_read_before(session_id, "run_command")
print(f"  尝试调用 run_command...")
print(f"  门禁结果: {'✅ 放行' if allowed else '⛔ 拦截'}")
print(f"  原因: {reason}")

# ── 场景4：任务完成，写日志 ──
print("\n【场景4】任务完成，写日志：")
result = write_diary(
    event="测试了AgentDiary门禁系统",
    lesson="门禁拦截有效，不读笔记确实不能动手",
    significance="important",
    context="MVP版本演示",
    agent="lyra",
)
print(f"  {result}")

# ── 场景5：写了日志，任务算完成 ──
print("\n【场景5】写了日志后，任务完成：")
allowed, reason = gate.check_write_after(session_id)
print(f"  门禁结果: {'✅ 任务完成' if allowed else '⛔ 未完成'}")
print(f"  原因: {reason}")

# ── 审计统计 ──
print("\n【审计统计】")
stats = gate.get_stats()
print(f"  今日任务总数: {stats['total_today']}")
print(f"  读笔记率: {stats['read_diary_rate']}")
print(f"  写日志率: {stats['write_diary_rate']}")

print("\n" + "=" * 60)
print("演示完成！")
print("=" * 60)
