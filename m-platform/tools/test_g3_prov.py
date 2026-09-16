# -*- coding: utf-8 -*-
"""G-3 来源域分离（prov）+ §3.1 目录行注入单测（09-14，plan-memory-v03-draft §3/§3.1 修正段）。

口径（§3.1 修正后，机械可判）：
- 注入面**永不注卡正文**：每张活跃卡只出一行 "- [memory:文件名] 标题"
  （标题=首个 # 标题，无则文件名；每行 ≤60 字符，总量 ≤2KB，超限截尾加 "...(目录截断)"）；
- prov 门保留且加码：delegated/inbox 卡连目录行都不出（文件名+标题+正文全都不许出现）；
- 活跃白名单：跳过 *.bak / *.md.bak / backup-* / . 开头文件（含 .reflect_last），不递归子目录（projects/）；
- facts-*.md 行级流水账不出目录行（维持不注入，按需 read）。

跑法（宿主）：D:/m/workspace/.venv/Scripts/python.exe D:/m/tools/test_g3_prov.py
跑法（容器，主会话执行，全部临时目录构造，不依赖真记忆/真信箱数据）：
  docker exec -i m-workplatform-1 python3 - < test_g3_prov.py

覆盖：端到端 _inject_work_rules（6）+ 目录行格式（4）+ 活跃白名单/不递归（7）+
流水账（2）+ 总量上限/522K 大文件（5）+ prov 判定辅助件（8，旧 H 组语义不变）。
"""
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "workspace"))

from scribe_hook import (  # noqa: E402
    ScribeMiddleware,
    prov_of_card,
    card_injectable,
    build_card_inject,
    card_toc_line,
    _CARD_LINE_MAX,
    _CARD_TOC_LIMIT,
)

ok = 0
fail = []


def check(name, cond):
    global ok
    if cond:
        ok += 1
        print(f"  ok {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name}")


def make_card(mem_dir, fname, fm, body):
    (mem_dir / fname).write_text(fm + body, encoding="utf-8")


def toc_lines(text):
    """从注入面/返回值里挑目录行（含 [memory: 标记的行）。"""
    return [ln for ln in text.splitlines() if "[memory:" in ln]


# ── 1) 端到端：临时卡 → _inject_work_rules → 断言注入面（§3.1 新语义）──
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    mem = root / "memory"
    mem.mkdir()
    # 四张卡：self 显式 / 缺省（无 frontmatter）/ delegated / inbox，标题与正文标记各不重叠
    make_card(mem, "card_self.md", "---\nname: cs\nprov: self\n---\n",
              "# 自家标题\nSELF-BODY-9a3 这句话绝不能进注入面。\n")
    make_card(mem, "card_default.md", "", "# 缺省标题\nDEFAULT-BODY-7k1 这句话绝不能进注入面。\n")
    make_card(mem, "card_deleg.md", "---\nname: cd\nprov: delegated\n---\n",
              "# 外派标题\nDELEG-BODY-4f8\n")
    make_card(mem, "card_inbox.md", "---\nname: ci\nprov: inbox\n---\n",
              "# 信箱标题\nINBOX-BODY-2q6\n")

    mw = ScribeMiddleware(root_dir=root)
    req = types.SimpleNamespace(system_prompt="BASE")
    mw._inject_work_rules(req)
    surface = req.system_prompt

    lines = toc_lines(surface)
    check("E2E-1 self 卡出目录行且正文不注入",
          any("card_self.md" in ln for ln in lines) and "SELF-BODY-9a3" not in surface)
    check("E2E-2 缺省卡（无 prov）出目录行且正文不注入",
          any("card_default.md" in ln for ln in lines) and "DEFAULT-BODY-7k1" not in surface)
    check("E2E-3 delegated 加码：连目录行都不出",
          "card_deleg" not in surface and "DELEG-BODY-4f8" not in surface
          and "外派标题" not in surface)
    check("E2E-4 inbox 加码：连目录行都不出",
          "card_inbox" not in surface and "INBOX-BODY-2q6" not in surface
          and "信箱标题" not in surface)
    check("E2E-5 WORK_RULES_INJECT 本体照旧（旧逻辑不动）", "【本轮工作规范" in surface)
    check("E2E-6 原有 system_prompt 不被吃掉", surface.startswith("BASE"))

# ── 2) 目录行格式：标题/回落/60 字符/不含正文 ──
with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    make_card(mem, "t1.md", "", "# 首标在这里\n- 正文句子 BODY-SENT-t1 不许出现在目录行。\n")
    make_card(mem, "t2.md", "", "纯流水正文没有 # 标题。\n")
    make_card(mem, "t3.md", "", "# " + "很长的标题" * 30 + "\n正文\n")
    out = build_card_inject(mem)
    lines = toc_lines(out)
    line_t1 = next((ln for ln in lines if "t1.md" in ln), "")
    line_t3 = next((ln for ln in lines if "t3.md" in ln), "")
    check("F-1 标题取首个 # 标题", "首标在这里" in line_t1 and line_t1.startswith("- [memory:t1.md]"))
    check("F-2 无 # 标题回落文件名", "t2.md" in out and "纯流水正文" not in out)
    check("F-3 长标题行 ≤60 字符硬截", 0 < len(line_t3) <= _CARD_LINE_MAX)
    check("F-4 目录行不含正文句子", "BODY-SENT-t1" not in out and "正文句子" not in line_t1)

# ── 3) 活跃白名单：备份/隐藏/backup-*/非 md/子目录 一律不列，正常卡照列 ──
with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    (mem / "projects").mkdir()
    make_card(mem, "keep.md", "", "# 正常卡\n")
    make_card(mem, "card_a.md.bak", "", "# 备份甲标题\ncard_a md bak 正文\n")
    make_card(mem, "notes.bak", "", "# 备份乙标题\n")
    make_card(mem, "backup-card.md", "", "# 备份丙标题\n")  # 实测顶层 522K 备份同款形态
    make_card(mem, ".reflect_last.md", "", "# 隐藏卡标题\n")
    (mem / ".reflect_last").write_text("09-14", encoding="utf-8")  # 无扩展名隐藏件
    make_card(mem, "readme.txt", "", "# 非 md\n")
    make_card(mem / "projects", "sub.md", "", "# 子目录卡标题\n")
    out = build_card_inject(mem)
    check("W-1 *.md.bak 被跳过", "card_a.md.bak" not in out and "备份甲标题" not in out)
    check("W-2 *.bak 被跳过", "notes.bak" not in out and "备份乙标题" not in out)
    check("W-3 backup-* 被跳过", "backup-card.md" not in out and "备份丙标题" not in out)
    check("W-4 点开头文件被跳过（含 .reflect_last）",
          ".reflect_last" not in out and "隐藏卡标题" not in out)
    check("W-5 非 .md 文件被跳过", "readme.txt" not in out)
    check("W-6 projects/ 子目录不递归", "sub.md" not in out and "子目录卡标题" not in out)
    check("W-7 白名单外不误伤：正常卡照列", "keep.md" in out and "正常卡" in out)

# ── 4) facts-*.md 流水账不出目录行（维持不注入，按需 read）──
with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    make_card(mem, "facts-2026-09.md", "", "# 流水标题\n- [09-14] 流水一条\n")
    make_card(mem, "facts-2026-09-backup-20260913.md", "", "# 流水备份标题\n")
    out = build_card_inject(mem)
    check("C-1 facts-*.md 流水账不出目录行", "facts-2026-09.md" not in out and "流水标题" not in out)
    check("C-2 facts-*backup* 复合形态也不出", "backup-20260913" not in out and "流水备份标题" not in out)

# ── 5) 机械上限：522K 大文件只出一行；多卡超 2KB 截尾加标记 ──
with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    make_card(mem, "huge.md", "", "# 巨型卡标题\n" + ("填充正文甲乙丙丁\n" * (522 * 1024 // 17))
              + "HUGE-SENTINEL-tail 句\n")
    out = build_card_inject(mem)
    lines = toc_lines(out)
    check("M-1 522K 大文件只出一行目录行",
          len(lines) == 1 and "huge.md" in lines[0] and "巨型卡标题" in lines[0])
    check("M-2 大文件正文一字不注入", "填充正文" not in out and "HUGE-SENTINEL-tail" not in out)

with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    n_cards = 80  # 每行 60 字符，80 行必超 2KB → 必须截尾
    for i in range(n_cards):
        make_card(mem, f"card_{i:02d}.md", "", "# " + f"卡{i:02d}" + "标" * 55 + "\n正文\n")
    out = build_card_inject(mem)
    lines = toc_lines(out)
    check("M-3 总量 ≤2KB 机械上限（UTF-8 字节）", len(out.encode("utf-8")) <= _CARD_TOC_LIMIT)
    check("M-4 超限截尾并加标记", "目录截断" in out)
    check("M-5 截尾后行数 < 卡数", 0 < len(lines) < n_cards)

with tempfile.TemporaryDirectory() as td:
    mem = Path(td)
    make_card(mem, "one.md", "", "# 唯一小卡\n")
    out = build_card_inject(mem)
    check("M-6 未超限时不加截断标记", "目录截断" not in out and "[memory:one.md]" in out)

# ── 6) prov 判定辅助件：门本体语义不变（旧 H 组照留）──
check("H-1 prov:self -> self", prov_of_card("---\nprov: self\n---\nx") == "self")
check("H-2 无 frontmatter -> 缺省 self", prov_of_card("纯正文") == "self")
check("H-3 frontmatter 无 prov 键 -> 缺省 self", prov_of_card("---\nname: a\n---\nx") == "self")
check("H-4 prov:delegated -> delegated", prov_of_card("---\nprov: delegated\n---\nx") == "delegated")
check("H-5 prov:inbox -> inbox", prov_of_card("---\nprov: inbox\n---\nx") == "inbox")
check("H-6 引号值 prov: 'inbox' -> inbox", prov_of_card("---\nprov: 'inbox'\n---\nx") == "inbox")
check("H-7 门放行 self", card_injectable("---\nprov: self\n---\nx") is True)
check("H-8 门拦 delegated", card_injectable("---\nprov: delegated\n---\nx") is False)

print(f"assertions: {ok + len(fail)} passed={ok} failed={len(fail)}")
print("ALL GREEN" if not fail else f"FAILURES: {fail}")
raise SystemExit(0 if not fail else 1)
