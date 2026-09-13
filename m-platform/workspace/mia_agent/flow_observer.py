"""FlowObserver —— 米娅动作序列观测器（流程体系 v2 层3，一期只观测不拦）。

数据基建：记录每个 run 的工具调用序列（tool+参数指纹+作用域判定），run 内累计
批准卡相关指标；为 30 题基线对比/归因三分类/AER 提供原始数据。
挂载：主图 middleware（ConfirmGateC1 之后）。子层不挂（牛马序列另有 auto_log）。

作用域断言（一期只记不拦——NOVA"先装眼睛再装手"）：
- 全盘 find（/ 起点无 maxdepth 限定）
- execute 命令引用 /data/mia_home 之外的绝对路径写操作（>, >>, tee, rm, mv 落点）
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from langchain.agents.middleware.types import AgentMiddleware

_FULL_FIND = re.compile(r"find\s+/(?:\s|$)")
_DATA_ROOT = "/data/mia_home"
_DEV_SINKS = ("/dev/", "/proc/self/")
# r43（hy4 Q2 全收：覆盖集/选项吞落点/fd 方向/变量目标/进程替换/mv 取末位）——
# 正则打地鼠终态是沙箱文件系统断言（v0.3），本层按"宁可 unresolved 标记不可静默"重构。
_SEG_SPLIT = re.compile(r"\s*(?:;|&&|\|\||\|)\s*")
_OPTS = re.compile(r"^-")
_REDIR = re.compile(r"(?:(\d+)?>>?)\s*(\S+)")
# 无重定向符号的写操作命令族（hy4 P0-a 清单）
_INPLACE_WRITERS = ("sed -i", "dd ", "tar -c", "install ", "ln -s", "unzip")


def _seg_write_targets(seg: str) -> list:
    """单段命令 → 写落点/标记清单。规则：
    >/>> 目标（含 fd 前缀，dev 设备除外）；rm 全部非选项参数；mv/cp 末位非选项；
    tee 后续参数；写命令族的落点参数；含 $ 或 ( 的目标 → unresolved: 标记。"""
    out = []
    toks = seg.split()
    if not toks:
        return out
    cmd = toks[0]
    # 1) 所有重定向目标（带或不带 fd 前缀统一收）
    for m in _REDIR.finditer(seg):
        fd, target = m.group(1), m.group(2).strip("'\"")
        if target.startswith(_DEV_SINKS):
            continue  # 2>/dev/null 等丢弃语义特赦（靠设备前缀，不靠 fd 号——hy4 P1-c）
        if re.match(r"^&\d*$", target):
            continue  # 2>&1 的 &1=fd 复制不是文件落点（r43）
        if target.startswith(">") or target.startswith("("):
            out.append("unresolved:procsub")
        elif "$" in target:
            out.append(f"unresolved:{target}")
        else:
            out.append(target)  # 1>/etc/a 与 2>>/etc/log 都是真写（fd 非 2 设备=不洗白）
    args = [t.strip("'\"") for t in toks[1:] if not _OPTS.match(t)]
    opts = " ".join(toks[1:])
    if cmd == "rm" and args:
        out.extend(a for a in args if "$" not in a)
        out.extend(f"unresolved:{a}" for a in args if "$" in a)
    if cmd in ("mv", "cp") and args:
        dest = args[-1]  # 落点=末位非选项参数（hy4 P1-f：原取首参=抓源不是抓的）
        out.append(dest if "$" not in dest else f"unresolved:{dest}")
    if cmd == "tee":
        out.extend(a for a in args if "$" not in a)
    if any(k in seg for k in ("sed -i", "ln -s")):
        if args:
            out.append(args[-1])  # sed -i/ln -s 目标在尾部
    if cmd == "dd":
        m = re.search(r"of=(\S+)", seg)
        if m:
            out.append(m.group(1))
    if cmd == "tar" and "-c" in opts:
        m = re.search(r"[\s\"](-{0,2}[a-zA-Z]*f[a-zA-Z]*)[\s=]+(\S+)", seg)
        if m:
            out.append(m.group(2))
    if cmd == "unzip":
        m = re.search(r"-d\s+(\S+)", seg)
        if m:
            out.append(m.group(1))
    return out


def _write_targets(blob: str) -> list:
    """execute 命令文本 → 全部写落点（含 unresolved 标记）。分段逐一提取。"""
    targets = []
    for seg in _SEG_SPLIT.split(blob):
        for t in _seg_write_targets(seg.strip()):
            if t not in targets:
                targets.append(t)
    return targets


class FlowObserver(AgentMiddleware):
    """记录序列+作用域预演断言。实例跨 run 共享，按 thread_id 分桶。
    继承官方 AgentMiddleware（裸类缺协议属性 trace_policy 等，10:2x 崩溃两连实证）。
    r42 台账批首件：每行 observe 同步落 jsonl（重启即丢已第 4 次实证——30 题
    中段批次数据至今无法回捞，本次基线全靠人肉盯屏记台账）。落盘失败绝不影响主流程。"""

    name = "flow_observer"
    _file_lock = threading.Lock()

    def __init__(self, max_buckets: int = 400, jsonl_path: str | Path | None = None):
        super().__init__()
        self._runs: dict = defaultdict(list)   # {tid: [ {tool, fp, ts, flags} ]}
        self._max = max_buckets
        self._dropped = 0                      # r43（hy4 Q4）：落盘失败计数——数据完整性可机械判定
        # r43（hy4 P1-1）：跨进程锁是假的——每 worker 进程独立文件（读时合并），
        # 彻底消掉 append 竞争与 Windows 共享冲突面。
        if jsonl_path:
            import os
            _jp = str(jsonl_path).replace("%PID%", str(os.getpid()))
            self._jsonl = Path(_jp)
        else:
            self._jsonl = None
        if self._jsonl:
            try:
                self._jsonl.parent.mkdir(parents=True, exist_ok=True)  # r43（P2-4）：建目录一次，不在热路径
            except Exception:
                pass

    @staticmethod
    def _tid() -> str:
        try:
            from langgraph.config import get_config
            return str((get_config().get("configurable") or {}).get("thread_id", ""))
        except Exception:
            return "NO-TID"

    @staticmethod
    def _fp(args) -> str:
        try:
            return hashlib.sha256(json.dumps(args or {}, ensure_ascii=False,
                                             sort_keys=True).encode()).hexdigest()[:12]
        except Exception:
            return "?"

    def _scope_flags(self, name: str, args) -> list:
        flags = []
        blob = ""
        if name == "execute":
            blob = str((args or {}).get("command") or "")
            if _FULL_FIND.search(blob):
                flags.append("full-find")
            for target in _write_targets(blob):
                if target.startswith("unresolved:"):
                    flags.append(target)  # r43（hy4 P1-d/e）：变量/进程替换目标宁可标记不可静默
                elif target.startswith("/") and not target.startswith(_DATA_ROOT):
                    flags.append(f"out-of-scope:{target}")
            # r47（Eve 炮3）：读行为路径形态也进序列（纯记不拦）——M2 方差收敛与
            # C1#3 探路复发共用同一数据源；写落点与 read-look 可双标，分析侧去重。
            try:
                from mia_agent.acceptance_kit import check_path_form
                for p in check_path_form(blob):
                    flags.append(f"read-look:{p}")
            except Exception:
                pass
        return flags

    def observe(self, name: str, args):
        rec = {"tool": name, "fp": self._fp(args), "ts": round(time.time(), 1),
               "flags": self._scope_flags(name, args)}
        # r61b（Lyra 预演件地基）：账里只有指纹=误杀复盘没语料——补动作原文截 120 字。
        # 隐私口径：120 字截断+这本账不出数据区（米娅可 grep notes/ 的自家账）。
        try:
            _a = args or {}
            _raw = (str(_a.get("command") or "") if name == "execute"
                    else str(_a.get("file_path") or ""))
            if _raw:
                rec["cmd"] = _raw[:120]
        except Exception:
            pass
        tid = self._tid()
        seq = self._runs[tid]
        seq.append(rec)
        if len(seq) > 2000:  # r43（hy4 P1-2）：单桶上限，丢最老半段留痕
            del seq[:1000]
            seq.append({"tool": "__truncated__", "fp": "?", "ts": rec["ts"], "flags": []})
        if len(self._runs) > self._max:  # 桶裁剪（R69 教训：慢泄漏堵死）
            for k in list(self._runs)[: self._max // 2]:
                self._runs.pop(k, None)
        if rec["flags"]:
            print(f"[flow-observer] ⚠ {tid} {name} flags={rec['flags']}", flush=True)
        self._persist(tid, rec)
        return rec

    def _persist(self, tid: str, rec: dict) -> None:
        """台账批首件：jsonl 追落盘（每进程独立文件+行内锁；失败计数不挡路）。"""
        if not self._jsonl:
            return
        try:
            line = json.dumps({"tid": tid, **rec}, ensure_ascii=False)
            with FlowObserver._file_lock:
                with open(self._jsonl, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            self._dropped += 1
            if self._dropped in (1, 10, 100):  # 出声节流：首次/10/100（持续失败要响，不刷屏）
                print(f"[flow-observer] 落盘失败 x{self._dropped}（不挡路）：{e}", flush=True)

    def summary(self, tid: str | None = None) -> dict:
        tid = tid or self._tid()
        seq = self._runs.get(tid) or []
        return {
            "steps": len(seq),
            "dropped_persist": self._dropped,  # r43 闸门3：基线收工先查此数=0 才认台账有效
            "tools": [r["tool"] for r in seq],
            "flags_total": sum(len(r["flags"]) for r in seq),
        }

    # ---- middleware 钩子（同步+异步双钩，awrap 教训） ----
    def wrap_tool_call(self, request, handler):
        tc = getattr(request, "tool_call", None) or {}
        self.observe(str(tc.get("name", "?")), tc.get("args"))
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        tc = getattr(request, "tool_call", None) or {}
        self.observe(str(tc.get("name", "?")), tc.get("args"))
        return await handler(request)


observer = FlowObserver(
    jsonl_path=Path(__file__).resolve().parent.parent / "mia_home" / "notes"
    / "flow_obs.%PID%.jsonl"  # r43（hy4 P1-1）：每 worker 进程独立文件，读时合并
)  # 模块级单例（graph.py 挂载用）；r42 观测序列落盘（数据区 notes/，米娅可自查）
