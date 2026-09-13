"""mia_agent.dept_watch —— 部门任务"完工/受阻"推送监视器（r25 军事链断点3修复，v2 扫描式）。

背景：主管链走官方 start_async_task 派部门，库不给 runs.create 挂 webhook——
部门 run 结束（包括"受阻请示"收尾）主线程永远不知道，链卡死无人报。

v2 设计（v11/v12 实锤教训：从工具返回抽 task_id 会撞 uuid 前缀/Command 结构不可靠）：
门放行 start_async_task 只登记"主线程 + 时间戳"；本监视器轮询 threads.search，
发现【该时刻之后新建的部门/总管线程】（metadata.graph_id ∈ dept_*/gm）run 结束且未通知
→ 唤醒主线程去 check_async_task 取报告转呈。两段式：请示唤醒一次，真完工再唤醒一次。

安全边界：只唤醒登记过的主线程；内存态 TTL 2h；进程内 SDK（X-Internal-Key=同进程钥匙），
零新 HTTP 面。
"""
import threading
import time

_WATCH: dict = {}       # main_tid -> {"at": float, "seen": set, "notified": set, "desc": str}
_LOCK = threading.Lock()
_TTL = 7200
_GRACE = 20             # 派活后至少等这么久再判"部门开张"
_INTERVAL = 15


def register(main_tid: str, desc: str = ""):
    """门放行 start_async_task 时登记发起主线程。"""
    if main_tid:
        # r55b 档位校验器（NOVA 提案）：register 就地定档（不依赖描述头——
        # start_async_task 的 task 文本才是派活真身，dispatch 标记头只在其自己链上）。
        try:
            from mia_agent.model_tier import classify_task
            _tier = classify_task(desc or "").get("tier", "")
        except Exception:
            _tier = ""
        # r56 缺口①（一条龙对账表）：任务文本里的"完成标志:"行提取登记，
        # 完工时与部门汇报做机械包含核对——汇报说完成≠标志达成（W5 教训外推到派活链）。
        _marks = [ln.split("完成标志:", 1)[1].strip()[:80]
                  for ln in (desc or "").splitlines() if "完成标志:" in ln]
        with _LOCK:
            _WATCH[main_tid] = {"at": time.time(), "seen": set(),
                                "notified": set(), "desc": (desc or "")[:500],
                                "tier": _tier,
                                "marks": _marks[:7]}
        print(f"[dept-watch] register main={main_tid} tier={_tier} marks={len(_marks)}", flush=True)


def _client():
    import os
    from langgraph_sdk import get_sync_client
    from internal_key import INTERNAL_KEY
    url = os.environ.get("MIA_SELF_SDK_URL", "http://127.0.0.1:8000")
    return get_sync_client(url=url, headers={"X-Internal-Key": INTERNAL_KEY})


def _is_dept_thread(th: dict) -> bool:
    gid = str((th.get("metadata") or {}).get("graph_id") or "")
    return gid.startswith("dept_") or gid == "gm"


def _scan():
    c = None
    while True:
        time.sleep(_INTERVAL)
        try:
            now = time.time()
            with _LOCK:
                for k in [k for k, v in _WATCH.items() if now - v["at"] > _TTL]:
                    _WATCH.pop(k, None)
                items = [(k, dict(v)) for k, v in _WATCH.items()]
            if not items:
                continue
            if c is None:
                try:
                    c = _client()
                except Exception:
                    continue
            try:
                ths = c.threads.search(limit=40)
            except Exception as e:
                print(f"[dept-watch] search 失败: {e}", flush=True)
                continue
            for main_tid, info in items:
                if now - info["at"] < _GRACE:
                    continue
                for th in ths:
                    tid = th.get("thread_id") or ""
                    if tid == main_tid or tid in info["seen"] or not _is_dept_thread(th):
                        continue
                    # v13 实锤修正：必须过滤"登记之后新建"的线程——否则历史遗留部门线程
                    # 会被当新任务唤醒（v13 撞中旧线程=侥幸内容恰好一致）
                    try:
                        import datetime as _dt
                        ca = str(th.get("created_at") or "")
                        if ca and _dt.datetime.fromisoformat(ca.replace("Z", "+00:00")).timestamp() < info["at"] - 2:
                            with _LOCK:
                                w = _WATCH.get(main_tid)
                                if w:
                                    w["seen"].add(tid)
                            continue
                    except Exception:
                        pass
                    try:
                        st = c.threads.get_state(tid)
                    except Exception:
                        continue
                    if st.get("next"):
                        continue                      # 还在跑，下轮再看
                    msgs = (st.get("values") or {}).get("messages") or []
                    if len(msgs) < 2:
                        with _LOCK:
                            _WATCH.get(main_tid, {}).get("seen", set()).add(tid)
                        continue                      # 空线程，永不再看
                    tail3 = " ".join(str(m.get("content", "")) for m in msgs[-3:])
                    stage = "请示" if ("⛔" in tail3 or "请示" in tail3) else "完工"
                    already = tid in info["notified"]
                    if already and stage != "完工":
                        continue                      # 请示提醒过，等真完工
                    with _LOCK:
                        w = _WATCH.get(main_tid)
                        if not w:
                            continue
                        w["seen"].add(tid)
                        if stage == "完工":
                            w["notified"].add(tid)
                    # r55 档位校验器：标档 vs 实际动作数对账落台账（NOVA"一期天天免费攒"）
                    if stage == "完工" and info.get("tier"):
                        try:
                            import json as _j
                            from pathlib import Path as _P
                            _f = _P(__file__).resolve().parent.parent / "mia_home" / "notes" / "tier_audit.jsonl"
                            _f.parent.mkdir(parents=True, exist_ok=True)
                            with open(_f, "a", encoding="utf-8") as _fh:
                                _fh.write(_j.dumps({"ts": round(time.time(), 1),
                                                    "tier": info["tier"], "steps": len(msgs),
                                                    "dept": tid[:8], "main": main_tid[:8]},
                                                   ensure_ascii=False) + "\n")
                        except Exception:
                            pass  # 校验账失败绝不挡汇报
                    try:
                        # r56 缺口①：完成标志机械包含核对（对部门末条汇报文本）——
                        # 未命中标志不拦停（部门可能有合理变通），但如实附注给米娅/爸爸看。
                        _mark_note = ""
                        if info.get("marks"):
                            _miss = [mk for mk in info["marks"] if mk not in tail3]
                            if _miss:
                                _mark_note = (f"【完成标志机械核对】{len(_miss)}/{len(info['marks'])} "
                                              f"条标志未在部门末条汇报中命中：" +
                                              "；".join(_miss[:3]) +
                                              "——用 check_async_task 取全文核对，未达成如实报，别替部门圆。")
                        c.runs.create(main_tid, "agent",
                            input={"messages": [{"role": "user", "content":
                                f"【部门自动汇报】检测到有部门任务（{info['desc'][:80] or '后台活'}）{stage}。"
                                + (_mark_note + " " if _mark_note else "") +
                                "用 list_async_tasks 核对你自己派出的任务状态，对已结束的逐个 check_async_task 取汇报，"
                                "按你的角色处理：调度层汇总后上报派活上级；主对话直接转呈爸爸"
                                "（若含待批准事项，把线程号与指纹〔fp:…〕原样转达，不要改写；"
                                "不认识的线程号如实说明，不要张冠李戴）。"}]},
                            config={"configurable": {"user_id": "dept-watch"}})
                        print(f"[dept-watch] 唤醒 main={main_tid} dept={tid} stage={stage}", flush=True)
                    except Exception as e:
                        print(f"[dept-watch] 唤醒失败: {e}", flush=True)
        except Exception:
            continue


def start():
    """graph.py 装配段调用一次；daemon 线程，随进程退出。"""
    threading.Thread(target=_scan, daemon=True, name="dept-watch").start()
