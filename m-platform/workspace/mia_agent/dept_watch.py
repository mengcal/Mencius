"""mia_agent.dept_watch —— 部门任务"完工/受阻"推送监视器（r25 军事链断点3修复，v2 扫描式）。

背景：组长链走官方 start_async_task 派部门，库不给 runs.create 挂 webhook——
部门 run 结束（包括"受阻请示"收尾）主线程永远不知道，链卡死无人报。

v2 设计（v11/v12 实锤教训：从工具返回抽 task_id 会撞 uuid 前缀/Command 结构不可靠）：
门放行 start_async_task 只登记"主线程 + 时间戳"；本监视器轮询 threads.search，
发现【该时刻之后新建的部门/调度线程】（metadata.graph_id ∈ dept_*/gm）run 结束且未通知
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
        with _LOCK:
            _WATCH[main_tid] = {"at": time.time(), "seen": set(),
                                "notified": set(), "desc": (desc or "")[:60]}
        print(f"[dept-watch] register main={main_tid}", flush=True)


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
                    try:
                        c.runs.create(main_tid, "agent",
                            input={"messages": [{"role": "user", "content":
                                f"【部门自动汇报】检测到部门线程 {tid}（{info['desc'] or '任务'}）{stage}。"
                                "用 check_async_task 查该线程最新汇报，按你的角色处理：调度层汇总后上报派活上级；"
                                "主对话直接转呈管理员（若含待批准事项，把线程号与指纹〔fp:…〕原样转达，不要改写）。"}]},
                            config={"configurable": {"user_id": "dept-watch"}})
                        print(f"[dept-watch] 唤醒 main={main_tid} dept={tid} stage={stage}", flush=True)
                    except Exception as e:
                        print(f"[dept-watch] 唤醒失败: {e}", flush=True)
        except Exception:
            continue


def start():
    """graph.py 装配段调用一次；daemon 线程，随进程退出。"""
    threading.Thread(target=_scan, daemon=True, name="dept-watch").start()
