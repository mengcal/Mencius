"""mia_agent.dept_watch —— 部门任务"完工/受阻"推送监视器（r25 军事链大考断点3修复）。

背景：组长链走官方 start_async_task 派部门，库不给 runs.create 挂 webhook——
部门 run 结束（包括"受阻请示"收尾）主线程永远不知道，链卡死无人报。
方案：确认门放行 start_async_task 时登记 {部门tid → 主线程tid}（同进程内存），
本监视器后台线程轮询：部门线程 run 结束 → 给主线程注入唤醒汇报指令，
助手随即 check_async_task（只读，已入白名单）取部门报告转呈管理员。

安全边界：唤醒消息只注入登记过的主线程；登记表内存态、2 小时超时清理；
注入走进程内 SDK（X-Internal-Key=同进程 internal_key，与 tasks_webhook 同款通道），
不新增任何 HTTP 面。
"""
import threading
import time

_WATCH: dict = {}          # dept_tid -> {"main": str, "desc": str, "at": float}
_LOCK = threading.Lock()
_TTL = 7200                # 登记最长存活 2h（异常部门不无限盯）
_GRACE = 45                # 派活宽限期：run 可能还没起来，next==[] 不等于完成
_INTERVAL = 20


def register(dept_tid: str, main_tid: str, desc: str = ""):
    """确认门放行 start_async_task 后调用：登记部门线程与发起主线程的映射。"""
    if dept_tid and main_tid and dept_tid != main_tid:
        with _LOCK:
            _WATCH[dept_tid] = {"main": main_tid, "desc": (desc or "")[:60], "at": time.time()}


def _client():
    import os
    from langgraph_sdk import get_sync_client
    from internal_key import INTERNAL_KEY
    url = os.environ.get("MIA_SELF_SDK_URL", "http://127.0.0.1:8000")
    return get_sync_client(url=url, headers={"X-Internal-Key": INTERNAL_KEY})


def _scan():
    c = None
    while True:
        time.sleep(_INTERVAL)
        try:
            now = time.time()
            with _LOCK:
                for k in [k for k, v in _WATCH.items() if now - v["at"] > _TTL]:
                    _WATCH.pop(k, None)
                items = list(_WATCH.items())
            if not items:
                continue
            if c is None:
                try:
                    c = _client()
                except Exception:
                    continue
            for dept_tid, info in items:
                if now - info["at"] < _GRACE:
                    continue
                try:
                    st = c.threads.get_state(dept_tid)
                except Exception:
                    continue
                if st.get("next"):
                    continue                      # 还在跑
                msgs = (st.get("values") or {}).get("messages") or []
                if len(msgs) < 2:
                    continue                      # 从未真正启动，交给 TTL 清理
                try:
                    c.runs.create(info["main"], "agent",
                        input={"messages": [{"role": "user", "content":
                            f"【部门自动汇报】你派出的部门任务（{info['desc'] or dept_tid[:8]}）"
                            "已执行完毕或停在请示上。用 check_async_task 查该部门线程的最新汇报，"
                            "把结果原样转呈管理员（若汇报里有待批准事项，把其中的线程号和指纹一并转达）。"}]},
                        config={"configurable": {"user_id": "dept-watch"}})
                except Exception:
                    continue
                with _LOCK:
                    _WATCH.pop(dept_tid, None)
        except Exception:
            continue


def start():
    """graph.py 装配段调用一次；daemon 线程，随进程退出。"""
    threading.Thread(target=_scan, daemon=True, name="dept-watch").start()
