"""
office.routers.misc —— /skills、/usage、/context、/stats、/health、/approvals、旧路径指引页（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :239-267   skills_lock 管理端点（GET /skills/list、POST /skills/rehash）
- :643-724   GET /usage/today、GET /context/threads、GET /stats
- :1106-1142 GET /health、POST /approvals、DELETE /approvals
- :1552-1574 /config（已删除指引）、/settings_page、/office、/（根跳转）

归属裁定：拆分方案 misc 清单里的 /models/all 与 providers 模块重复，实际落在 routers/providers.py
（读 external.providers[].models_cache，同源聚合），本模块不注册，避免同路径双注册。

依赖说明：/stats 复用 tasks.py 的 TASKS/_lock（横向引用，非反向 import app）；_token_audit 来自 core。
注：原 :1148 的 `import json as _json` 延迟导入提到顶部（/usage、/context 需要）。
"""
import json as _json  # 原 :1148（提到顶部）

import skills_lock as _skills_lock  # 原 :240

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, FileResponse  # 原 :1149

from ..core import BASE, _token_audit
from . import tasks as _tasks_mod  # R10.9（hy4 P1-2）：必须走模块属性访问——tasks._prune 会 global 重绑定 TASKS，from-import 会拿到旧账本对象

router = APIRouter()

_SKILLS_DIR = BASE / "mia_home" / "skills"  # 原 :241（原 Path(__file__).parent=workplatform 根；包化后改用 BASE，语义等价）


@router.get("/skills/list")
async def skills_list():
    """技能清单+校验状态（设置页「技能清单」卡消费；audit_on=False 不刷审计）。"""
    if not _skills_lock.enabled():
        return {"enabled": False, "clean": True, "files": []}
    manifest = _skills_lock.ensure_baseline(_SKILLS_DIR)
    bad = _skills_lock.verify(_SKILLS_DIR, manifest, audit_on=False)
    okset = set(manifest) - set(bad["missing"]) - set(bad["mismatch"])
    files = [{"name": rel, "hash": h[:12],
              "status": "✓" if rel in okset else "✗"}
             for rel, h in sorted(manifest.items())]
    files += [{"name": rel, "hash": "", "status": "未登记"} for rel in bad["extra"]]
    return {"enabled": True, "clean": not (bad["missing"] or bad["mismatch"] or bad["extra"]),
            "files": files}


@router.post("/skills/rehash")
async def skills_rehash():
    """管理员在宿主改完 D:\\m\\skills 后重扫重建基线（管理员 token 门内）。
    注：图构建时校验的是启动快照——重建后如技能被停用状态未恢复，重启一次即生效。"""
    if not _skills_lock.enabled():
        return {"ok": False, "error": "skills_lock 未启用（设置页先开启）"}
    manifest = _skills_lock.rehash(_SKILLS_DIR)
    return {"ok": True, "count": len(manifest), "note": "基线已重建；若此前技能被停用，重启后生效"}


@router.get("/usage/today")
async def usage_today():
    """今日 token 消耗（读 mia_home/usage.jsonl，按 model 汇总；R45 观测台数据源）。"""
    import datetime
    f = BASE / "mia_home" / "usage.jsonl"
    today = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()).isoformat()
    agg: dict = {}
    total = {"input": 0, "output": 0, "total": 0, "calls": 0}
    if f.exists():
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(line)
                except Exception:
                    continue
                if r.get("date") != today:
                    continue
                a = agg.setdefault(r.get("model", "unknown"), {"input": 0, "output": 0, "total": 0, "calls": 0})
                for k in ("input", "output", "total"):
                    v = int(r.get(k, 0) or 0)
                    a[k] += v
                    total[k] += v          # 累加本条增量，不是模型累计值（修 评审B#2/评审A 用量虚高）
                a["calls"] += 1
                total["calls"] += 1
        except Exception as e:
            return {"error": str(e)}
    return {"date": today, "by_model": agg, "total": total}


@router.get("/context/threads")
async def context_threads():
    """R53 上下文容量图数据源：usage.jsonl 按线程取最近一次模型调用的 input_tokens。
    基线（系统提示词+工具+技能）取全部记录中的最小 input 估算；差额即对话消息。"""
    f = BASE / "mia_home" / "usage.jsonl"
    LIMITS = {"glm-4.7": 200000, "glm-4.5-air": 131072, "glm-4.6v": 65536}
    per: dict = {}
    all_inputs = []
    if f.exists():
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(line)
                except Exception:
                    continue
                tid = r.get("thread") or ""
                inp = int(r.get("input", 0) or 0)
                if not tid or inp <= 0:
                    continue
                all_inputs.append(inp)
                ts = r.get("ts") or ""
                cur = per.get(tid)
                if not cur or ts >= cur["ts"]:
                    per[tid] = {"thread": tid, "model": r.get("model", ""), "input": inp, "ts": ts}
        except Exception as e:
            return {"error": str(e)}
    baseline = min(all_inputs) if all_inputs else 0
    out = []
    for t in per.values():
        limit = LIMITS.get(t["model"], 131072)
        msgs = max(t["input"] - baseline, 0)
        out.append({**t, "limit": limit, "baseline": baseline, "messages": msgs,
                    "pct": round(t["input"] / limit * 100, 1) if limit else 0})
    out.sort(key=lambda x: x["ts"], reverse=True)
    return {"baseline": baseline, "threads": out[:10]}


@router.get("/stats")
async def stats():
    """工作平台并发/排队状态（R69：改吃 TASKS 官方派活账本——/runs 旧机器已退役）。"""
    with _tasks_mod._lock:
        statuses = {}
        for r in _tasks_mod.TASKS.values():
            s = r.get("status", "?")
            statuses[s] = statuses.get(s, 0) + 1
        total = len(_tasks_mod.TASKS)
    return {
        "运行中": statuses.get("running", 0),
        "排队中": statuses.get("queued", 0),
        "已完成": statuses.get("done", 0),
        "失败": statuses.get("error", 0),
        "总任务数": total,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "service": "后台任务队列", "agent": "worker"}


@router.post("/approvals")
async def api_approve(req: dict = Body(...), request: Request = None):
    """R69 确认门 v2（评审C A1）：管理员的外部批准——与模型重试不可辨的问题在此解耦：
    批准只认【模型之外】的来源。本机 curl / 汇报卡按钮 → 该线程该工具下一次调用放行一次。
    R10.3（评审B 🟡A 时窗调包）：请求须带拦截消息里的指纹 fp——与登记不符=拒（"参数已变"），
    绝不静默重绑最新被拦的那条；无登记=拒（不覆盖已有批准，防误点/连点杀死有效批准）。
    R10.12（管理员裁决）：X-By: admin 作废——常数头零熵（R69 时代无统一 token 的遗产），
    真锁=中间件 api_token_guard（/approvals 全程 token fail-closed），拆假锁不再给人双保险错觉。"""
    import approvals as _ap
    tid, tool = str(req.get("thread_id", "")), str(req.get("tool", ""))
    if not tid or not tool:
        return {"error": "需要 thread_id 与 tool"}
    ok, why = _ap.approve(tid, tool, str(req.get("fp") or ""))
    _token_audit("approval_granted" if ok else "approval_denied", ok,
                 tool=tool, tid=tid[:8],
                 ip=(request.client.host if request and request.client else "?"),
                 why=why)  # R10.5（评审B 遗留）：批准动作带来源标注入审计
    return {"ok": ok, "reason": why, "approved": f"{tid[:8]}…:{tool}" if ok else ""}


@router.delete("/approvals")
async def api_revoke(req: dict = Body(...), request: Request = None):
    """R10.3（评审B ⚪E）：撤销未消费的批准/拦截登记——误点有后悔药，不再悬 24h 等助手兑现。
    r25：X-By 同 approve 作废，门=token（中间件）。"""
    import approvals as _ap
    tid, tool = str(req.get("thread_id", "")), str(req.get("tool", ""))
    if not tid or not tool:
        return {"error": "需要 thread_id 与 tool"}
    return {"ok": _ap.revoke(tid, tool)}


# ── R2.1（2026-08-29 作者）：旧配置系统已删除 ──
# config.json / /config 接口 / office_settings.html 全部移除，统一走 /settings*（settings_mgr.py）。
# 若有人访问旧路径，返回明确指引。

@router.get("/config")
async def get_config():
    return {"deprecated": True, "message": "此接口已删除，请改用 /settings"}

@router.post("/config")
async def set_config(cfg: dict = Body(...)):
    return {"deprecated": True, "message": "此接口已删除，请改用 POST /settings/{section}"}

@router.get("/settings_page")
async def settings_page():
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/docs">设置页已迁移至 deep-agents-ui 的 /settings 路由')

@router.get("/office")
async def office_page():
    return FileResponse(BASE / "office.html", media_type="text/html")

@router.get("/")
async def root():
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/office">')
