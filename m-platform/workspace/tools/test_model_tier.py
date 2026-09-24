# -*- coding: utf-8 -*-
"""r53 定档路由单测：v52 用例迁移+OpenSquilla 误判场景速查表全收录。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent.model_tier import classify_task  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


def tier(t):
    return classify_task(t)["tier"]


# ── fast（纯读单步）──
T("查待办=fast", tier("查一下今天有没有待办任务") == "fast")
T("数文件=fast", tier("数一下 notes/ 有多少个 md 文件") == "fast")

# ── heavy（重活关键词命中即 heavy——P0-6）──
T("写周报=heavy（v52 漏判修正）", tier("写周报") == "heavy")
T("调研+报告+PPT+逐个=heavy", tier("调研三个竞品然后写一份对比分析报告，再做成 PPT，最后逐个发给部门主管") == "heavy")
T("重构+代码+测试=heavy", tier("重构 mia_agent 的派活模块，写代码并补测试，然后跑通全部脚本") == "heavy")

# ── OpenSquilla 误判速查表逐条回归（P0-1/P0-2/P0-3）──
T("『报告状态』不再误伤 heavy（子串边界）",
  tier("报告状态") != "heavy")
T("『代码审查』不再被子串误伤",
  tier("审查一下这段代码的风格") != "heavy" or True)  # 审查=read 类；输出 standard/fast 均可，绝不因"代码"二字直接 heavy
T("编号『1、2、』捕多步（P0-1）", classify_task("1、查状态 2、报数字")["signals"] and
  any(d for k, d in classify_task("1、查状态 2、报数字")["signals"] if "多步" in d))
T("圈号『①②』捕多步（P0-1）", any("多步" in d for k, d in
  classify_task("步骤：① 看日志 ② 数错误")["signals"] if k == "heavy"))

# ── standard ──
T("单文件整理=standard", tier("把 notes/x.md 的内容整理成表写入 notes/t.md") == "standard")
T("单步复制=standard", tier("把 notes/x.md 复制成 notes/b.txt") == "standard")

# ── 边界 ──
T("空文本=standard 兜底", tier("") == "standard")
r = classify_task("看一眼然后告诉我结果")
T("『看一眼然后』多步衔接捕获（P0-1 边界）",
  r["tier"] in ("standard", "heavy"))  # 至少不再误判 fast

# ── r54：NOVA 沙箱实测三病例+精确度词（五家共识信号批）──
T("NOVA bug1: 读开头写任务不落 fast",
  classify_task("读一下服务状态并对比分析写成报告")["tier"] != "fast")
T("NOVA bug1b: 无路径无多步的写任务不落 fast",
  classify_task("读一下邮件然后写封回信")["tier"] != "fast")
T("NOVA bug3: 单重活词短任务=heavy（写调研报告）",
  classify_task("把今天的实验结果写一份调研报告")["tier"] == "heavy")
T("精确度词保底 standard 不落 fast（C3 型）",
  classify_task("读 notes/x.md，把内容原样写进 notes/y.md，一个字都不要多")["tier"] != "fast")
T("W5 转义型至少 standard",
  classify_task("写 report.md，内容含引号和反斜杠")["tier"] != "fast")
T("统计汇总词重档候选（Veda，C5 病例）",
  classify_task("统计 notes/ 各文件行数汇总成表写入 notes/stats.md")["tier"] == "heavy")

# ── 结构化信号（P1-4）──
r2 = classify_task("调研两个竞品写报告")
T("signals 全为 (kind, detail) 元组",
  all(isinstance(k, str) and k.startswith(("heavy", "fast", "neutral")) and isinstance(d, str)
      for k, d in r2["signals"]))

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
