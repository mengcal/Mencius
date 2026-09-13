# -*- coding: utf-8 -*-
"""model_tier —— 派活定档路由 v53（OpenSquilla 双审迭代版）。

v52→v53 迭代（审点全收）：
  - 信号结构化：[(kind, detail)] 元组（P0-4/P0-5/P1-4——评分不再解析中文字符串）
  - 关键词边界：命中处前后须为非中文字符（标点/空格/行界），"报告状态"不再误伤（P0-2/P0-3）
  - 编号正则扩展：1、2、3、/①②③/一、二、三、全捕（P0-1）
  - 门槛调平：重活关键词命中即 heavy（"写周报"=heavy，质量优先宁高勿低，P0-6）；
    fast 要求 短+单步+零重活信号（P0-7）
  - 正则预编译 + 档位分布计数器（P2-4/P2-6，二期准确率分析用）
档位语义不变：fast=纯读单步免费快档 / standard=默认主力 / heavy=GLM 档。
一期只标不切：dispatch 派活时档位写进任务描述头，二期有准确率数据再硬切选模。
"""
from __future__ import annotations

import re

from mia_agent.acceptance_kit import extract_literals
from mia_agent.task_brief import verb_class

# 重活关键词：命中任一即 heavy（质量优先宁高勿低——P0-6）
_HEAVY_HINTS = ("报告", "周报", "文档", "ppt", "幻灯", "代码", "脚本", "工程", "重构",
                "调研", "综述", "对比分析", "翻译", "长文", "多份", "逐个")
_FAST_HINTS = ("查一下", "看一眼", "数一下", "报个数", "状态", "有几个", "列出")
# r54（四家共识信号）：精确度词——命中=保底 standard 防 fast（C3/W5 病例：精确密集
# 的重是"精确密集"不是"能力密集"，核对由 literal_diff 验收网兜）
_PRECISION_HINTS = ("原样", "逐字", "一个字不多", "严格", "必须", "不要改", "核对", "验证")
_MULTI_STEP = re.compile(r"(然后|再|接着|第二步|之后|顺序|[一二三四五六七八九十]、|\d+、|[①②③④⑤⑥])")
# 中文边界近似：命中处前后不能是中文字符（"报告状态"的"报告"前是行首✓后是"状"✗→不命中）
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _hint_hit(text: str, hint: str) -> bool:
    # r53b：纯子串命中——误伤由"动词类联合判定"消解（动词主导：报告状态=read 不升档，
    # 写周报=create 升档），文本边界启发式在中文复合词（写周报/做报告）前双向失效，已撤。
    return hint.lower() in text.lower()


_TIER_STATS = {"fast": 0, "standard": 0, "heavy": 0}  # P2-6：档位分布计数器（二期准确率分析）


def classify_task(task_text: str) -> dict:
    """任务文本 → {"tier": fast|standard|heavy, "signals": [(kind, detail)], "vc": 动词类}。
    结构化信号 kind∈{heavy, fast, neutral}——评分只看 kind 不看中文串（P0-4 收编）。"""
    text = str(task_text or "")
    signals = []  # [(kind, detail)]
    vc = verb_class(text)
    lit = extract_literals(text)
    n_paths = len(lit["paths"])
    n_quotes = len(lit["quotes"])
    long_text = len(text) >= 80
    multi_step = bool(_MULTI_STEP.search(text))

    if vc == "read":
        signals.append(("fast", "动词类=read"))
    if n_paths >= 2:
        signals.append(("neutral", f"路径字面量{n_paths}"))  # r53c：双路径=常规文件操作不算重活
    if n_quotes >= 2:
        signals.append(("neutral", f"引文字面量{n_quotes}"))  # r54（Cora 死信号炮）：引文=精确度敏感，走 precision 通道不计 heavy
    if long_text:
        signals.append(("heavy", f"描述长{len(text)}字"))
    if multi_step:
        signals.append(("heavy", "含多步衔接"))
    heavy_hits = [h for h in _HEAVY_HINTS if _hint_hit(text, h)]
    if heavy_hits and vc != "read":
        # r53（OpenSquilla 速查表『报告状态』案）：重活名词×动词类联合判定——
        # 动词主导（"写周报"写=create→heavy；"报告状态"报=read→不因名词升档）；
        # 纯文本边界在中文复合词前失效（"写周报"的"写"挡住"周报"）。
        signals.append(("heavy", "重活关键词:" + "/".join(heavy_hits[:3])))
    fast_hits = [h for h in _FAST_HINTS if _hint_hit(text, h)]
    if fast_hits and vc == "read":
        signals.append(("fast", "快查关键词:" + "/".join(fast_hits[:2])))
    # r54（五家共识信号批）：精确度词/统计汇总词/写类否决
    precision_hits = [h for h in _PRECISION_HINTS if h in text]
    if precision_hits:
        # NOVA 裁定：精确密集的正确解=保底 standard（防 fast）而非冲 heavy——
        # C3/W5 病例的重是"精确密集"不是"能力密集"，机械核对由 literal_diff 兜
        signals.append(("neutral-precision", "精确度词:" + "/".join(precision_hits[:3])))
    if vc in ("create", "modify", "delete", "copy"):
        signals.append(("neutral-write", f"写类动词={vc}"))  # Veda：写类天然不进 fast
    # r54（NOVA bug1 主修）：读写动词混合=非纯读（"读一下…写成报告"敞口封死）——
    # verb_class 取最早动词会漏掉后置写动词，这里独立扫多动词类并存。
    _vcs = set()
    for cls, words in (("read", ("读", "看", "查", "数", "统计", "列", "找")),
                       ("create", ("写", "新建", "创建", "生成")),
                       ("modify", ("改", "追加", "更新", "整理")),
                       ("delete", ("删", "清除", "移除"))):
        if any(w in text for w in words):
            _vcs.add(cls)
    if {"read", "create"} <= _vcs or {"read", "modify"} <= _vcs:
        signals.append(("heavy", "读写混合任务"))

    heavy_n = sum(1 for k, _ in signals if k == "heavy")
    fast_n = sum(1 for k, _ in signals if k == "fast")
    is_write = any(k == "neutral-write" for k, _ in signals)
    is_precision = any(k == "neutral-precision" for k, _ in signals)
    stats_hit = any(w in text for w in ("统计", "汇总", "合计"))  # Veda：C5 病例——统计类是读+算+写复合活

    # 判定唯一真源=结构化信号计数（r53b：原裸看 heavy_hits 与联合判定两处打架——
    # "报告状态"vc=read 不因名词升档；"写周报"vc=create 一票即 heavy）
    if heavy_n >= 2 or (heavy_n >= 1 and vc != "read") or stats_hit:
        tier = "heavy"          # P0-6：重活关键词命中即 heavy（宁高勿低）；统计类专道（C5 实锤）
    elif (fast_n >= 1 and not multi_step and n_paths <= 1 and not long_text
          and heavy_n == 0 and vc == "read" and not is_precision):
        # r54（五家共识）：fast 只切读类——写类动词显式排除（Veda）+精确度词排除（NOVA）
        tier = "fast"
    elif is_precision and tier_is_standard_floor(heavy_n, vc):
        tier = "standard"       # 精确度词=保底 standard（NOVA：验收网在 literal_diff）
    else:
        tier = "standard"
    try:
        _TIER_STATS[tier] += 1
    except Exception:
        pass
    return {"tier": tier, "signals": signals, "vc": vc}


def tier_is_standard_floor(heavy_n: int, vc: str) -> bool:
    """精确度词保底 standard 的判据（r54）：无 heavy 票或仅读动词时兜住。"""
    return heavy_n == 0 or vc == "read"


def tier_stats() -> dict:
    """档位分布计数（P2-6，二期准确率分析数据源）。"""
    return dict(_TIER_STATS)
