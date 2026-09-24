# -*- coding: utf-8 -*-
"""dept_watch 汇报环行为测（09-15 家底盲区补测一期，WIKI 盲区账第1条）。

此前状态：v2 扫描式监视器**行为零覆盖**——军事链命根子（部门 run 结束→唤醒主线程转呈）。
本件全 mock：FakeClient 顶替 langgraph_sdk（threads.search/get_state/runs.create），
假时钟顶替 time.time/sleep，__file__ 重定向顶替 tier_audit 台账落盘面。
零活体：不 start() 线程、不连 8000/2024、不碰真实 mia_home。
SystemExit 穿 _scan 的 while True（其外层 except Exception 不吞 SystemExit）= 圈数可控。
"""
import contextlib
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))  # 宿主=D:\m\workspace，容器=.../src，同样成立

import mia_agent.dept_watch as dw  # noqa: E402

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


class _Threads:
    def __init__(self, owner): self._o = owner

    def search(self, limit=40):
        return list(self._o.thread_list)

    def get_state(self, tid):
        self._o.get_state_calls.append(tid)
        seq = self._o.state_map.get(tid) or [{}]
        return seq.pop(0) if len(seq) > 1 else seq[0]


class _Runs:
    def __init__(self, owner): self._o = owner

    def create(self, tid, aid, input=None, config=None):
        if self._o.runs_create_raises:
            raise RuntimeError("mock 唤醒失败")
        self._o.wakes.append({"tid": tid, "aid": aid, "input": input, "config": config})


class FakeClient:
    """threads.search / threads.get_state / runs.create 三面替身，全留痕。"""

    def __init__(self):
        self.thread_list = []
        self.state_map = {}      # tid -> [round0, round1, ...] 逐次弹出
        self.wakes = []
        self.get_state_calls = []
        self.runs_create_raises = False
        self.threads = _Threads(self)
        self.runs = _Runs(self)


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()


def _dept_th(tid, created_ts=None, graph_id="dept_0"):
    return {"thread_id": tid,
            "metadata": {"graph_id": graph_id},
            "created_at": _iso(created_ts) if created_ts else ""}


def _state(tail_contents, next_pending=None):
    msgs = [{"content": c} for c in tail_contents]
    return {"next": next_pending, "values": {"messages": msgs}}


TMP = Path(tempfile.mkdtemp(prefix="zdept_watch_"))
T0 = 1_700_000_000.0  # 假钟起点


def scenario(main_tid="mainA", desc="", at=T0):
    """登记一条 watch（假钟冻结在 at），返回 (client, holder)。"""
    client = FakeClient()
    holder = {"t": at}
    with patch.object(dw.time, "time", lambda: holder["t"]):
        dw._WATCH.pop(main_tid, None)
        dw.register(main_tid, desc)
        with dw._LOCK:
            if main_tid in dw._WATCH:
                dw._WATCH[main_tid]["at"] = at
    return client, holder


def drive(client, holder, rounds=1, advance=0.0):
    """跑 rounds 圈 _scan：每圈前假钟 +advance；圈数耗尽 SystemExit 收工。"""
    calls = {"n": 0}

    def fake_sleep(_iv):
        calls["n"] += 1
        if calls["n"] > rounds:
            raise SystemExit
        holder["t"] += advance

    with patch.object(dw.time, "sleep", fake_sleep), \
         patch.object(dw.time, "time", lambda: holder["t"]), \
         patch.object(dw, "_client", lambda: client), \
         patch.object(dw, "__file__", str(TMP / "mia_agent" / "dept_watch.py")):
        with contextlib.suppress(SystemExit):
            dw._scan()


# ── ① register 后部门完工 → 恰一次唤醒，消息含【部门自动汇报】 ──
dw._WATCH.clear()
c, h = scenario(desc="写一份周报给爸爸\n完成标志: 产出 reports/weekly.md")
th = _dept_th("deptT1", created_ts=T0 + 3)
c.thread_list = [th]
c.state_map["deptT1"] = [_state(["干活", "周报已产出 reports/weekly.md"])]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("①完工唤醒恰一次", len(c.wakes) == 1)
T("①唤醒打到登记主线程", c.wakes and c.wakes[0]["tid"] == "mainA"
  and c.wakes[0]["aid"] == "agent")
T("①消息含【部门自动汇报】", c.wakes and "【部门自动汇报】"
  in c.wakes[0]["input"]["messages"][0]["content"])
T("①消息嵌入任务描述", c.wakes and "写一份周报"
  in c.wakes[0]["input"]["messages"][0]["content"])
T("①config.user_id=dept-watch", c.wakes
  and c.wakes[0]["config"]["configurable"]["user_id"] == "dept-watch")

# tier_audit 台账落 __file__ 派生路径（=TMP，真实 mia_home 零污染）
ta = TMP / "mia_home" / "notes" / "tier_audit.jsonl"
T("①tier 台账落到重定向盘（完工+有档位）", ta.is_file())
if ta.is_file():
    rec = json.loads(ta.read_text(encoding="utf-8").splitlines()[0])
    T("①台账字段齐", rec.get("tier") and "steps" in rec and "dept" in rec)
else:
    T("①台账字段齐", False)

# ①追加：完成标志全部命中 → 无机械核对附注
T("①标志全命中不带附注", c.wakes and "完成标志机械核对"
  not in c.wakes[0]["input"]["messages"][0]["content"])

# ── ①b 标志未命中 → 附注出现（r56 缺口①） ──
dw._WATCH.clear()
c, h = scenario(desc="整理台账\n完成标志: 已写入 stats.md")
c.thread_list = [_dept_th("deptT1b", created_ts=T0 + 3)]
c.state_map["deptT1b"] = [_state(["干活", "整理好了"])]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
_w = c.wakes[0]["input"]["messages"][0]["content"] if c.wakes else ""
T("①b未命中出附注", "【完成标志机械核对】1/1" in _w and "已写入 stats.md" in _w)

# ── ② 请示帧唤醒一次；完工帧应再唤醒一次（v2 两段式，notified 集语义） ──
dw._WATCH.clear()
c, h = scenario(desc="部署脚本")
c.thread_list = [_dept_th("deptT2", created_ts=T0 + 3)]
c.state_map["deptT2"] = [
    _state(["准备动作", "⛔ 需要批准删除缓存，请示"]),   # 第1圈：请示帧
    _state(["准备动作", "已批准", "删除完成，任务完工"]),  # 第2圈：完工帧
]
drive(c, h, rounds=2, advance=dw._GRACE + 5)
T("②请示帧唤醒恰一次", len(c.wakes) >= 1
  and all("请示" in w["input"]["messages"][0]["content"] for w in c.wakes[:1]))
T("②完工帧再唤醒一次（两段式）", len(c.wakes) == 2
  and "完工" in c.wakes[-1]["input"]["messages"][0]["content"])
# 09-15 dwfix 裁决：取证格翻转为永久正钉——修复后完工帧必须二次 get_state（seen 门只吞终结线程）；
# 若未来有人把请示帧再塞进 seen，本格转红即报警（主会话签字翻转，工兵不动钉守纪在案）。
T("②两段式二次读态（dwfix 正钉）", len(c.get_state_calls) == 2)

# ── ③ v13 修正回归钉：created_at 早于登记时刻的旧线程被 seen 吞掉 ──
dw._WATCH.clear()
c, h = scenario(desc="新活")
c.thread_list = [_dept_th("oldTh", created_ts=T0 - 100)]
c.state_map["oldTh"] = [_state(["m1", "旧线程早已完工"])]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("③旧线程零唤醒", len(c.wakes) == 0)
T("③旧线程入 seen 且不查 state",
  "oldTh" in dw._WATCH["mainA"]["seen"] and c.get_state_calls == [])
# created_at 缺失宽容（v13 过滤 try 失败=照常判定，不挡新线程）
dw._WATCH.clear()
c, h = scenario(desc="新活2")
th_noca = _dept_th("noCa", created_ts=None)
c.thread_list = [th_noca]
c.state_map["noCa"] = [_state(["m1", "完工咯"])]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("③b created_at 缺失照常唤醒（宽容钉）", len(c.wakes) == 1)

# ── ④ GRACE 期内不判 ──
dw._WATCH.clear()
c, h = scenario(desc="刚派活")
c.thread_list = [_dept_th("deptT4", created_ts=T0 + 1)]
c.state_map["deptT4"] = [_state(["m1", "完工"])]
drive(c, h, rounds=1, advance=0.0)  # now-at=0 < GRACE
T("④GRACE 内零唤醒", len(c.wakes) == 0 and c.get_state_calls == [])
T("④GRACE 内条目不被 TTL 清", "mainA" in dw._WATCH)

# ── ⑤ TTL 过期出 _WATCH ──
dw._WATCH.clear()
c, h = scenario(at=T0)                      # 旧条目：将过期
c2, _ = scenario(main_tid="mainB", at=T0 + 7199)  # 新条目：仍存活
c.thread_list = c2.thread_list = []
holder = {"t": T0 + dw._TTL + 10}
drive(c, holder, rounds=1)
with dw._LOCK:
    keys = set(dw._WATCH.keys())
T("⑤TTL 过期出 _WATCH", "mainA" not in keys)
T("⑤未过期条目存活", "mainB" in keys)

# ── ⑥ register 时 tier/marks 提取 ──
dw._WATCH.clear()
desc6 = ("写一份周报并对比分析上月数据\n"
         "完成标志: 产出 reports/weekly.md\n"
         "完成标志:   带空格的标志   \n"
         + "\n".join(f"完成标志: m{i}" for i in range(10)))
c, h = scenario(desc=desc6)
with dw._LOCK:
    w = dict(dw._WATCH["mainA"])
T("⑥tier 已定档（classify_task 纯函数）",
  w["tier"] in ("fast", "standard", "heavy") and bool(w["tier"]))
T("⑥marks 逐行提取+strip", w["marks"][:2] == ["产出 reports/weekly.md", "带空格的标志"])
T("⑥marks 上限 7 条", len(w["marks"]) == 7)
dw._WATCH.clear()
long_mark = "完成标志: " + "标" * 100
c, h = scenario(desc="做文档\n" + long_mark)
with dw._LOCK:
    w = dict(dw._WATCH["mainA"])
T("⑥单条标志截 80 字", len(w["marks"][0]) == 80)
T("⑥desc 留档截 500", len(w["desc"]) <= 500)

# ── 杂项钉 ──
# 非部门线程（graph_id=agent）与主线程本身不参与
dw._WATCH.clear()
c, h = scenario(desc="活")
c.thread_list = [_dept_th("mainA", created_ts=T0 + 1, graph_id="agent"),
                 _dept_th("otherMain", created_ts=T0 + 1, graph_id="agent")]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("非 dept 线程不触发", c.get_state_calls == [] and len(c.wakes) == 0)
T("_is_dept_thread：dept_*/gm 真、agent 假",
  dw._is_dept_thread({"metadata": {"graph_id": "dept_3"}})
  and dw._is_dept_thread({"metadata": {"graph_id": "gm"}})
  and not dw._is_dept_thread({"metadata": {"graph_id": "agent"}})
  and not dw._is_dept_thread({}))
# 空线程（msgs<2）永不再看
dw._WATCH.clear()
c, h = scenario(desc="活2")
c.thread_list = [_dept_th("emptyTh", created_ts=T0 + 1)]
c.state_map["emptyTh"] = [_state(["只有一条"])]
drive(c, h, rounds=2, advance=dw._GRACE + 5)
T("空线程零唤醒且入 seen", len(c.wakes) == 0
  and "emptyTh" in dw._WATCH["mainA"]["seen"]
  and c.get_state_calls == ["emptyTh"])
# 还在跑（next 非空）不唤醒
dw._WATCH.clear()
c, h = scenario(desc="活3")
c.thread_list = [_dept_th("runTh", created_ts=T0 + 1)]
c.state_map["runTh"] = [_state(["m1", "m2"], next_pending=("node",))]
drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("next 非空不唤醒不入 seen", len(c.wakes) == 0
  and "runTh" not in dw._WATCH["mainA"]["seen"])
# runs.create 抛异常被吞、循环不断
dw._WATCH.clear()
c, h = scenario(desc="活4")
c.runs_create_raises = True
c.thread_list = [_dept_th("boomTh", created_ts=T0 + 1)]
c.state_map["boomTh"] = [_state(["m1", "完工"])]
with contextlib.suppress(Exception):
    drive(c, h, rounds=1, advance=dw._GRACE + 5)
T("唤醒失败被吞不炸环", c.wakes == [] and "boomTh" in dw._WATCH["mainA"]["seen"])
# register 空 main_tid 无效
dw._WATCH.clear()
dw.register("", "desc")
T("空 main_tid 不登记", dw._WATCH == {})

dw._WATCH.clear()
print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
