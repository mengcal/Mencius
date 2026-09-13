# -*- coding: utf-8 -*-
"""task_brief —— 层2 任务简报件（09-13 夜窗 r44b：按 hy4 二审 P0/P1 修正）。

一物三用：① 验收 acceptance（机械提取，role 三标见 acceptance_kit）
② 换任务判定=**新 target 出现**（r44b-P0-2：不用集合相等——任何字面量增减都
   换题=回血无界；"看 a.md"窄化追问 a.md 已在场=不换题不回血）
③ 软重置带衰减（P1-6：回血额度 4→3→2→1→0，连续换题刷卡收敛；审计 print 出声）。

规则（全钉自 hy4 病例）：
  - 空 sig 分支：verb_class 变化才算换题（"删掉它"=delete≠modify→换题；
    "继续/嗯"=无动词类→同任务）；clarify 一律 True 不继承（P1-3 铁律不可继承）。
  - acceptance_for 返回 dict 列表（P0-1 契约：与 literal_diff 的 it.get 对齐）。
  - _briefs/软重置计数均进程内存——当前部署 langgraph-api 为线程池（进程内共享）
    有效；若未来 workers>1 需外置（P1-8 记录在案，docstring 即告警）。
"""
from __future__ import annotations

import threading
import time

_lock = threading.RLock()
_briefs: dict = {}  # {tid: {"goal_sig","created_ts","turn","done","clarify","verb_class"}}

# 机械动词类表（hy4 Q1 修法②）：换题判定用"动词类跳变"，空 sig 才查它
_VERB_CLASS = (
    ("delete", ("删", "去掉", "移除", "清除", "清空")),
    ("create", ("新建", "创建", "写入", "写到", "记到", "存到", "写")),
    ("modify", ("改", "修改", "追加", "补充", "更新", "整理")),
    ("copy", ("复制", "拷贝", "备份")),
    ("read", ("读", "看", "数", "统计", "查", "找", "列", "报")),
)


def verb_class(text: str) -> str:
    # 取"句中最早出现的动词类"（r44b 病例：『再加一份备份，删掉旧版』主句在前，
    # 表序先撞 delete 会记错类）
    best, pos = "", len(text) + 1
    for cls, words in _VERB_CLASS:
        for w in words:
            i = text.find(w)
            if 0 <= i < pos:
                best, pos = cls, i
    return best


def _fp_set(lit: dict) -> frozenset:
    return frozenset(
        [("path", v, r) for v, r in lit["paths"]] +
        [("quote", v, r) for v, r in lit["quotes"]] +
        [("num", v, "target") for v in lit["numbers"][:6]])


def _targets(sig: frozenset) -> set:
    return {t for t in sig if t[2] == "target"}


def note_task(task_text: str, tid: str, n_human: int) -> dict:
    """新 human 任务入简报（gate after_model 调用）。返回：
    {"new","clarify","literals"(dict 列表),"goal_sig","vc"}
    new=出现新 target（P0-2）或动词类跳变（空 sig 分支，Q1）；
    clarify=写类任务无验收目标（铁律：任何分支不继承"已明确"以外的判定，
    空 sig 追问一律 clarify=True——要问就问，别拿旧账验新活）。
    """
    from mia_agent.acceptance_kit import extract_literals
    lit = extract_literals(task_text)
    sig = _fp_set(lit)
    vc = verb_class(task_text)
    with _lock:
        if len(_briefs) > 500:
            for k in sorted(_briefs, key=lambda k: _briefs[k]["created_ts"])[:200]:
                _briefs.pop(k, None)
        cur = _briefs.get(tid)
        if cur is None:
            is_new, final_clarify = True, lit["needs_clarification"]
        elif not sig:
            # 空字面量消息："继续/嗯"=同任务；动词类跳变（"删掉它"）=换题
            is_new = bool(vc) and vc != cur.get("verb_class", "")
            sig = frozenset() if is_new else cur["goal_sig"]
            # 换题但无目标=必须问清对象（绝不拿旧账验收）；纯"嗯/继续"=继承现澄清态
            final_clarify = True if is_new else cur.get("clarify", False)
        else:
            # r44b-Q1 修法①：换题判据=出现新 target（集合相等误判"窄化追问"为换题，
            # 且字面量增减即回血=Q3 无界路径的门槛）；动词类跳变只在空 sig 分支判。
            new_t = _targets(sig) - _targets(cur["goal_sig"])
            is_new = bool(new_t)
            final_clarify = (lit["needs_clarification"] if is_new
                             else (lit["needs_clarification"] or cur.get("clarify", False)))
        brief = {"new": is_new,
                 "clarify": final_clarify,
                 "goal_sig": sig, "vc": vc,
                 "literals": [{"kind": k, "value": v, "role": r} for k, v, r in sorted(sig)]}
        if is_new:
            _briefs[tid] = {"goal_sig": sig, "created_ts": time.time(),
                            "turn": n_human, "done": False,
                            "clarify": final_clarify, "verb_class": vc}
        else:
            cur["turn"] = n_human
            cur["clarify"] = final_clarify
            cur["verb_class"] = vc or cur.get("verb_class", "")
    return brief


def mark_done(tid: str) -> None:
    with _lock:
        b = _briefs.get(tid)
        if b:
            b["done"] = True


def get_brief(tid: str) -> dict | None:
    with _lock:
        return dict(_briefs[tid]) if tid in _briefs else None


def acceptance_for(tid: str) -> list:
    """当前任务的验收清单——dict 列表（P0-1 契约修复：与 literal_diff 输入对齐）。"""
    with _lock:
        b = _briefs.get(tid)
    if not b:
        return []
    return [{"kind": k, "value": v, "role": r} for k, v, r in sorted(b["goal_sig"])]
