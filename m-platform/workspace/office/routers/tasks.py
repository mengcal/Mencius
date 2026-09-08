"""
office.routers.tasks —— TASKS 账本 + /tasks/dispatch|webhook|list + /files/save + /threads/title（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :39-40     _lock（守 TASKS 的模块级锁；misc 的 /stats 亦复用）
- :79-149    /runs 退役说明 + TASKS 账本/持久化/序号恢复 + _sdk_client
- :152-165   POST /files/save
- :277       _DISPATCH_HITS（/tasks/dispatch 限频窗）
- :463-640   _WHBK + _webhook_url + POST /tasks/dispatch + POST /tasks/webhook + GET /tasks/list
- :1577-1613 POST /threads/title

注：misc.py 的 /stats 依赖本模块的 TASKS/_lock（横向引用，非反向 import app，允许）。
"""
import asyncio
import os
import threading

from fastapi import APIRouter, Body, Request

from settings_mgr import token_ok as _token_ok  # 原 :1161（/tasks/dispatch 管理员 Bearer 认一）

from ..core import BASE, _JSONResp, _rate_ok

router = APIRouter()

# ---- R69：RUNS/信号量/线程池机器随 /runs 一起退役（五路评审"C 泄漏"清理）；_lock 留下守 TASKS ----
_lock = threading.Lock()


# ── R69（评审 评审E二.2.5"无鉴权派活后门"）：/runs 三端点 + 线程池机器已退役下线 ──
# 派活唯一正门 = 官方 start_async_task（AsyncSubAgent 五工具）+ /tasks/dispatch webhook 汇报。
# 前端与助手提示词均无调用方（grep 实锤），保留 = 白给的攻击面 + 死代码。


# ===== R3 第二阶段：独立线程后台长任务（2026-08-30 作者）=====
# 助手把大活 dispatch 到全新线程上后台跑，对话线程完全不被占用；
# 跑完后前端轮询发现，自动把结果喂回对话让助手汇报——"干完主动汇报"闭环。
# 机制全是官方的：langgraph SDK 的 threads.create + runs.create(background)。

TASKS: dict[str, dict] = {}
_TSEQ = 0
_webhook_lock = asyncio.Lock()  # R59：webhook 重复投递并发竞态锁（防同一任务重复注入汇报刷屏）
# R55：任务流水持久化（重启不丢，观测台/工人岗进程面板数据源）
_TASKS_FILE = BASE / "mia_home" / "tasks.json"


def _load_tasks_persisted():
    try:
        import json as _j
        if _TASKS_FILE.exists():
            data = _j.loads(_TASKS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_tasks():
    """TASKS 变更后落盘（观测台与工人岗进程面板的历史记录来源）。
    R69（C 泄漏清理）：裁剪到最新 200 条（bk 号数值序），文件/内存都不无限胖。"""
    try:
        import json as _j
        global TASKS
        if len(TASKS) > 200:
            try:
                keep = sorted(TASKS.keys(), key=lambda k: int(k.split("_")[1]) if "_" in k and k.split("_")[1].isdigit() else 0)[-200:]
            except Exception:
                keep = list(TASKS)[-200:]
            TASKS = {k: TASKS[k] for k in keep}
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TASKS_FILE.write_text(_j.dumps(TASKS, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


TASKS.update(_load_tasks_persisted())

# 从已恢复的任务号推最大序号，防重启后新任务 bk_001 覆盖旧记录（评审B#6）
for _k in list(TASKS.keys()):
    try:
        _n = int(str(_k).rsplit("_", 1)[-1])
        if _n > _TSEQ:
            _TSEQ = _n
    except Exception:
        pass


def _sdk_client():
    # R80（评审C b 纵深）：langgraph 原生 API 已挂 auth 模块。
    # R10.8（评审C P0-2）：guard 模式下本进程不持明文（get_api_token 恒空）——进程内合法调用
    # 改带【进程身份钥匙】X-Internal-Key（internal_key 模块级内存变量，助手 shell 进程拿不到），
    # auth 豁免=回环+该钥匙双条件。未配置密钥时（首部署 bootstrap 期）同样由此豁免。
    from langgraph_sdk import get_client
    from settings_mgr import get_api_token
    from internal_key import INTERNAL_KEY
    _tok = get_api_token()
    return get_client(url="http://localhost:8000",
                      headers={"X-Internal-Key": INTERNAL_KEY,
                               **({"Authorization": f"Bearer {_tok}"} if _tok else {})})


@router.post("/files/save")
async def files_save(req: dict = Body(...)):
    """前端上传的文件落到平台磁盘 mia_home/files/（R3：识图等后端直接按路径读）。
    只允许 http/https 之外的本地文件名，b64 内容由前端传。"""
    import base64 as _b64
    name = (req.get("name") or "").strip()
    b64 = req.get("b64") or ""
    if not name or not b64 or "/" in name or "\\" in name or ".." in name:
        return {"error": "需要 name（纯文件名）和 b64"}
    d = BASE / "mia_home" / "files"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(_b64.b64decode(b64))
    # 返回 workplatform 容器内路径（/vision 的 image_path 直接可用）
    return {"ok": True, "path": str(d / name)}


_DISPATCH_HITS: list = []  # R10.5：/tasks/dispatch 派活限频窗（60s ≤20）

# R79（hy4 复检：webhook 无鉴权=可伪造"自动汇报"跨线程注入管理员对话）：langgraph 服务端回调必须带
# 内部钥匙 w（URL 由本进程拼装、回调原样带回）。沙箱/助手没有 WEBHOOK_TOKEN env=伪造不了；未配置=拒（fail-closed）。
_WHBK = os.environ.get("WEBHOOK_TOKEN", "")


def _webhook_url(tid: str) -> str:
    return f"http://workplatform:8000/tasks/webhook?tid={tid}&w={_WHBK}"


@router.post("/tasks/dispatch")
async def tasks_dispatch(req: dict = Body(...), request: Request = None):
    """把大活派到独立后台线程：{"task": "任务描述"}。立即返回，不阻塞对话。"""
    task = (req.get("task") or "").strip()
    if not task:
        return {"error": "需要 task"}
    # R80 续（评审B/评审C/hy3 三方同指）：/tasks/dispatch 无门=同网容器可白嫖派活+main_thread 回注。
    # 双钥匙门（≤15 行）：Bearer 管理员密钥（浏览器/管理端）**或** X-Internal-Key=WEBHOOK_TOKEN
    # （进程内 dispatch_background_task 工具自带）二认一；都验不过 401。沙箱没钥匙也没 env=死路。
    import hmac as _h2
    ah = request.headers.get("authorization", "") if request else ""
    ptok = ah[7:].strip() if ah.lower().startswith("bearer ") else (request.headers.get("x-token") or "" if request else "")
    ik = (request.headers.get("x-internal-key") or "") if request else ""
    if not (_token_ok(ptok) or (_WHBK and _h2.compare_digest(_WHBK.encode(), str(ik).encode()))):
        return _JSONResp({"ok": False, "error": "派活需要管理员密钥或内部钥匙（浏览器走 Bearer，工具走 X-Internal-Key）"}, status_code=401)
    # R10.5（评审B 遗留清单·dispatch 限频）：滑动窗口 60s≤20——派活=起真线程烧真模型，
    # 被刷爆=后台线程池+上游额度双烧；与三扇代理门独立计数（互不挤兑）。
    if not _rate_ok(_DISPATCH_HITS, 60.0, 20):
        return _JSONResp({"ok": False, "error": "派活限流：每 60 秒最多 20 单，稍后再试"}, status_code=429)
    # R80（评审C P3）：回调钥匙未配置时直接拒绝派活——否则任务跑完回调 401、汇报静默丢
    # （工人岗干完活才发现话送不回=最坏的失败时机；宁可派活时就说清）
    if not _WHBK:
        return {"error": "WEBHOOK_TOKEN 未配置：后台任务回调会失败。请在 .env 配好并重启后再派活。"}
    main_thread = (req.get("main_thread") or "").strip()  # R3：发起对话的线程，完成后自动回去汇报
    global _TSEQ
    _TSEQ += 1
    tid = f"bk_{_TSEQ:03d}"
    from datetime import datetime as _dt
    TASKS[tid] = {"id": tid, "task": task, "status": "starting", "result": "", "main_thread": main_thread,
                  "created": _dt.now().strftime("%m-%d %H:%M")}
    try:
        client = _sdk_client()
        assistants = await client.assistants.search(graph_id="agent", limit=1)
        assistant_id = assistants[0]["assistant_id"] if assistants else "agent"
        thread = await client.threads.create(metadata={
            "cow_task": True,  # R57：工人岗任务线程标记（前端侧栏过滤）
            "custom_title": f"🐂 {task[:36]}" + ("…" if len(task) > 36 else ""),
        })
        run = await client.runs.create(
            thread["thread_id"], assistant_id,
            input={"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"background_task_enabled": True},  # R3 护栏：后台线程禁止再派活
                    "recursion_limit": 150},  # R45：深度调研多工具循环，默认 25 步必撞墙
            multitask_strategy="enqueue",
            # R3 官方 webhook：后台 run 一结束，langgraph 服务端主动 POST 这里（R79 带内部钥匙 w）
            webhook=_webhook_url(tid),
        )
        TASKS[tid].update({"thread_id": thread["thread_id"], "run_id": run["run_id"], "status": "running"})
        _save_tasks()
        return {"ok": True, "id": tid, "thread_id": thread["thread_id"]}
    except Exception as e:
        TASKS[tid]["status"] = "error"
        TASKS[tid]["result"] = str(e)[:300]
        _save_tasks()
        return {"error": f"派发失败: {e}"}


@router.post("/tasks/webhook")
async def tasks_webhook(tid: str = "", main: str = "", request: Request = None):
    """R3 官方 webhook 接收端（runs.create 的 webhook 参数，服务端 run 结束后主动 POST）。
    支持两种来源：① /tasks/dispatch 派的单（tid 在 TASKS 里）② 直派 SDK 单（query 带 main=主线程，
    报文里带 thread/run 信息）。更新任务状态；有主线程就 runs.create 唤醒助手主动汇报。"""
    # R79（hy4 复检）：内部回调钥匙校验，fail-closed——未配 token 或 w 不配对一律 401。
    # 旧版无鉴权+直派分支（main/body 里的 thread_id、run_id 全取自请求体）=沙箱内一条 curl
    # 可把任意线程的最后一条消息洗成"[工作者调度·自动汇报]"注进管理员的主对话（跨线程提示注入）。
    # R80：w 比对改常数时间（与 sandbox_runner/main token 同一套 compare_digest，防时序侧信道）。
    w = ""
    try:
        w = request.query_params.get("w") or ""
    except Exception:
        pass
    import hmac as _hmac
    if not _WHBK or not _hmac.compare_digest(_WHBK.encode(), str(w).encode()):
        return _JSONResp({"ok": False, "error": "webhook 内部钥匙不匹配"}, status_code=401)
    t = TASKS.get(tid)
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if not t:
        # 直派单（未走 /tasks/dispatch）：从参数与报文恢复信息
        bthread = body.get("thread_id") or (body.get("config") or {}).get("thread_id") or ""
        brun = body.get("run_id") or ""
        if main and (bthread or brun):
            t = {"id": tid or "sdk", "task": "（直派任务）", "status": "running", "result": "",
                 "main_thread": main, "thread_id": bthread, "run_id": brun}
            TASKS[tid or f"sdk_{bthread[:8]}"] = t
            _save_tasks()
    if not t:
        return {"ok": True}
    try:
        client = _sdk_client()
        run = await client.runs.get(t["thread_id"], t["run_id"])
        if run["status"] == "success":
            state = await client.threads.get_state(t["thread_id"])
            msgs = (state.get("values") or {}).get("messages", [])
            _last = msgs[-1] if msgs else None
            _content = (_last.get("content") if isinstance(_last, dict) else getattr(_last, "content", "")) if _last is not None else ""
            t["result"] = str(_content or _last)[:2000] if _last is not None else "（无输出）"  # R68 修 评审A E2：dict 消息取 content，不再序列化整字典
            t["status"] = "done"
        elif run["status"] in ("error", "timeout", "interrupted"):
            t["status"] = "error"
            t["result"] = f"后台任务异常退出（{run['status']}）"
    except Exception as e:
        t["result"] = t.get("result") or str(e)[:200]
    _save_tasks()
    mt = t.get("main_thread")
    # R58 三重防重：① reported 先置位再注入（webhook 重投递不再重复）② 注入前扫目标线程
    #    已有同单汇报则跳过 ③ 注入异常也保留 reported（失败走 /tasks/list 补查，不刷屏）
    # R59 并发锁：webhook 网络重试可能多投递并发到达，"检查→置位→注入"必须原子化，
    #    否则同一任务会被注入多次、助手重复汇报（2026-08-31 bk_001 实测复现）
    if mt and t["status"] in ("done", "error"):
        async with _webhook_lock:
            if t.get("reported"):
                return {"ok": True, "skipped": "已汇报过"}
            t["reported"] = True
            _save_tasks()
            try:
                client = _sdk_client()
                # 先扫目标线程：已有同单汇报就不重复注入（webhook 至少投递一次语义的保险）
                state = await client.threads.get_state(mt)
                msgs = (state.get("values") or {}).get("messages", [])
                marker = f"[工作者调度·自动汇报] 后台任务 {tid} "
                if any(str(getattr(m, "content", m.get("content") if isinstance(m, dict) else "")).startswith(marker) for m in msgs):
                    print(f"[webhook] {tid} 已有汇报记录，跳过重复注入", flush=True)
                    return {"ok": True, "skipped": "已存在"}
                assistants = await client.assistants.search(graph_id="agent", limit=1)
                aid = assistants[0]["assistant_id"] if assistants else "agent"
                verdict = "已完成" if t["status"] == "done" else "异常结束"
                await client.runs.create(
                    mt, aid,
                    input={"messages": [{"role": "user", "content":
                        f"[工作者调度·自动汇报] 后台任务 {tid} {verdict}。\n成果/情况：\n{t.get('result', '')[:1500]}\n"
                        f"请把结果要点汇报给管理员（别复述全文），然后继续陪他聊。"}]},
                    multitask_strategy="enqueue",
                )
            except Exception:
                pass  # 汇报失败不影响任务本身；/tasks/list 仍可查
    return {"ok": True}


@router.get("/tasks/list")
async def tasks_list():
    """后台任务列表（顺便轮询更新状态；完成的任务抓取最终结果）。"""
    try:
        client = _sdk_client()
        for t in TASKS.values():
            if t["status"] == "running" and t.get("thread_id") and t.get("run_id"):
                try:
                    run = await client.runs.get(t["thread_id"], t["run_id"])
                    if run["status"] == "success":
                        state = await client.threads.get_state(t["thread_id"])
                        msgs = (state.get("values") or {}).get("messages", [])
                        _last = msgs[-1] if msgs else None
                        _content = (_last.get("content") if isinstance(_last, dict) else getattr(_last, "content", "")) if _last is not None else ""
                        t["result"] = str(_content or _last)[:2000] if _last is not None else "（无输出）"  # R68 修 评审A E2
                        t["status"] = "done"
                    elif run["status"] in ("error", "timeout", "interrupted"):
                        t["status"] = "error"
                        t["result"] = f"后台任务异常退出（{run['status']}）"
                except Exception:
                    pass  # 单个查不动不影响列表
    except Exception:
        pass
    with _lock:
        return {"tasks": list(TASKS.values())}


@router.post("/threads/title")
async def threads_title(req: dict = Body(...)):
    """R45 自动起名：新对话首轮结束后前端调用。已有 custom_title 或还没有用户消息则跳过。
    标题用工人岗同款 glm-4.5-air（免费包，thinking off，一次 ~100 token），≤12 字写回 metadata。"""
    try:
        tid = (req.get("thread_id") or "").strip()
        if not tid:
            return {"ok": False, "error": "需要 thread_id"}
        client = _sdk_client()
        th = await client.threads.get(tid)
        meta = th.get("metadata") or {}
        if meta.get("custom_title"):
            return {"ok": True, "title": meta["custom_title"], "skipped": "已有标题"}
        state = await client.threads.get_state(tid)
        msgs = (state.get("values") or {}).get("messages", [])
        # R68 修 评审A E1/评审E三.2.1：get_state 的 messages 是 dict 列表，getattr 恒拿不到 type
        _mt = lambda m: m.get("type") if isinstance(m, dict) else getattr(m, "type", "")
        _mc = lambda m: m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        human = next((m for m in msgs if _mt(m) == "human"), None)
        if not human:
            return {"ok": True, "skipped": "还没有用户消息"}
        from providers import make_model
        from settings_mgr import load_agents_config
        _ac = load_agents_config()
        _tc = _ac.get("scribe") or _ac.get("boss") or {}
        m = make_model(_tc.get("provider", ""), _tc.get("model", ""), thinking="off", temperature=0.3)
        prompt = ("给这段对话起一个不超过12个字的标题，概括用户的核心意图。"
                  "只输出标题本身，不要引号不要句号。\n\n用户说："
                  + str(_mc(human))[:300])
        r = await m.ainvoke(prompt)
        title = str(getattr(r, "content", "")).strip().strip('"“”').replace("\n", "")[:24]
        if not title:
            return {"ok": False, "error": "模型没给出标题"}
        await client.threads.update(tid, metadata={"custom_title": title})
        return {"ok": True, "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e)}
