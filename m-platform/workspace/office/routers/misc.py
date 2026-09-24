"""
office.routers.misc —— /skills、/usage、/context、/stats、/health、/approvals、旧路径指引页（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :239-267   skills_lock 管理端点（GET /skills/list、POST /skills/rehash；W3 增 /skills/create|update|delete）
- :643-724   GET /usage/today、GET /context/threads、GET /stats
- :1106-1142 GET /health、POST /approvals、DELETE /approvals
- :1552-1574 /config（已删除指引）、/settings_page、/office、/（根跳转）

归属裁定：拆分方案 misc 清单里的 /models/all 与 providers 模块重复，实际落在 routers/providers.py
（读 external.providers[].models_cache，同源聚合），本模块不注册，避免同路径双注册。

依赖说明：/stats 复用 tasks.py 的 TASKS/_lock（横向引用，非反向 import app）；_token_audit 来自 core。
注：原 :1148 的 `import json as _json` 延迟导入提到顶部（/usage、/context 需要）。
"""
import json as _json  # 原 :1148（提到顶部）
import os  # W3：技能目录 realpath 前缀校验
import re  # W3：技能名白名单
import shutil  # W3：删技能目录
import threading  # r51b reflect daemon 用（模块级统一）
from pathlib import Path  # W3：技能路径运算

import skills_lock as _skills_lock  # 原 :240

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, FileResponse  # 原 :1149

from ..core import BASE, _token_audit
from . import tasks as _tasks_mod  # R10.9（hy4 P1-2）：必须走模块属性访问——tasks._prune 会 global 重绑定 TASKS，from-import 会拿到旧账本对象

router = APIRouter()

_SKILLS_DIR = BASE / "mia_home" / "skills"  # 原 :241（原 Path(__file__).parent=workplatform 根；包化后改用 BASE，语义等价）

# W3：技能名白名单——只许小写字母/数字/-/_，2-41 位，首字符限字母或数字（天然拒 "/" 与 ".."，堵路径穿越）。
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


def _skill_dir(name: str):
    """技能名 → 目录 Path（非法返回 None）。白名单正则 + realpath 前缀双保险（必须正好落在 _SKILLS_DIR 之下）。"""
    n = str(name or "").strip()
    if not _SKILL_NAME_RE.match(n):
        return None
    base = Path(os.path.realpath(_SKILLS_DIR))
    d = Path(os.path.realpath(base / n))
    if d.parent != base:  # 白名单已挡穿越；此处再确认没有借软链/相对路径跑出技能目录
        return None
    return d


def _parse_skill_md(md: Path):
    """解析 SKILL.md → (name, description, body)。body=正文（去掉 frontmatter），供设置页编辑回显。
    逐行解析，不引 yaml 依赖。"""
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", "", ""
    lines = text.splitlines()
    name = desc = ""
    body = text.strip("\n")
    if lines and lines[0].strip() == "---":
        end = None
        for i, ln in enumerate(lines[1:], start=1):
            if ln.strip() == "---":
                end = i
                break
            if ":" not in ln:
                continue
            k, _, v = ln.partition(":")
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k == "name" and not name:
                name = v
            elif k == "description" and not desc:
                desc = v
        if end is not None:
            body = "\n".join(lines[end + 1:]).strip("\n")
    return name, desc, body


def _render_skill_md(name: str, description: str, content: str) -> str:
    """拼出 <name>/SKILL.md 全文：frontmatter(name/description) + 正文。"""
    desc = (description or "").replace("\n", " ").strip()
    body = (content or "").replace("\r\n", "\n").strip("\n")
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n"


def _discover_skills() -> list:
    """扫 _SKILLS_DIR 下的顶层技能目录（含 SKILL.md）名列表。"""
    base = Path(_SKILLS_DIR)
    if not base.is_dir():
        return []
    return [p.name for p in sorted(base.iterdir()) if p.is_dir() and (p / "SKILL.md").is_file()]


def _after_skill_change(name: str, removed: bool = False) -> dict:
    """W3：技能文件改动后更新 skills_lock 基线并回新哈希。

    r27 评审 P2（Eve B2 尾注 + Veda 耦合提醒，知夏采纳）：旧实现调 rehash() 全目录重建
    基线——workplatform 挂载改 rw 后这就是洗白洞：任何一次合法写操作会把越权者偷偷
    塞进技能目录的文件一并"登记为合法"。现改为【只并入/摘除本次变更条目】：
    基线其余条目原样保留，未登记的 extra 仍会在 verify 报出、由爸爸 rehash 定夺。"""
    if not _skills_lock.enabled():
        return {"rehashed": False, "reason": "skills_lock 未启用，跳过重登记"}
    rel = f"{name}/SKILL.md"
    md = Path(_SKILLS_DIR) / rel
    manifest = _skills_lock.ensure_baseline(_SKILLS_DIR)
    if removed or not md.is_file():
        manifest.pop(rel, None)
        new_hash = ""
    else:
        new_hash = _skills_lock._sha256(md)
        manifest[rel] = new_hash
    mp = _skills_lock._manifest_path()
    try:
        tmp = mp.with_name(mp.name + ".tmp")
        tmp.write_text(_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(mp))
        _skills_lock.audit("skill_entry_update", f"{rel} {'removed' if (removed or not md.is_file()) else new_hash[:12]}")
    except Exception as e:
        return {"rehashed": False, "reason": f"基线写入失败：{str(e)[:60]}"}
    bad = _skills_lock.verify(_SKILLS_DIR, manifest, audit_on=False)
    return {"rehashed": True, "hash": new_hash[:12],
            "clean": not (bad["missing"] or bad["mismatch"] or bad["extra"])}


@router.get("/skills/list")
async def skills_list():
    """技能清单+校验状态（设置页「技能清单」卡消费；audit_on=False 不刷审计）。
    W3：每项技能=一个目录里的 SKILL.md，附 frontmatter description 与整体校验状态。"""
    if not _skills_lock.enabled():
        return {"enabled": False, "clean": True, "files": [], "skills": []}
    manifest = _skills_lock.ensure_baseline(_SKILLS_DIR)
    bad = _skills_lock.verify(_SKILLS_DIR, manifest, audit_on=False)
    okset = set(manifest) - set(bad["missing"]) - set(bad["mismatch"])
    files = [{"name": rel, "hash": h[:12],
              "status": "✓" if rel in okset else "✗"}
             for rel, h in sorted(manifest.items())]
    files += [{"name": rel, "hash": "", "status": "未登记"} for rel in bad["extra"]]
    # W3 技能卡数据：磁盘上的顶层技能目录 ∪ 基线里的顶层 <name>/SKILL.md
    # r27 评审 P2-8（CB）：基线键必须过技能名白名单才进列表——被篡改的 manifest
    # 曾可用 "../x/SKILL.md" 让下面 Path 拼接读到技能目录外一层。
    manifest_skills = {rel[: -len("/SKILL.md")] for rel in manifest
                       if rel.endswith("/SKILL.md")
                       and _SKILL_NAME_RE.match(rel[: -len("/SKILL.md")])}
    skills = []
    for n in sorted(manifest_skills | set(_discover_skills())):
        rel = f"{n}/SKILL.md"
        if rel in manifest:
            status, h = ("✓" if rel in okset else "✗"), manifest[rel][:12]
        else:
            status, h = "未登记", ""
        _, desc, body = _parse_skill_md(Path(_SKILLS_DIR) / rel)
        skills.append({"name": n, "description": desc, "body": body, "hash": h, "status": status})
    return {"enabled": True, "clean": not (bad["missing"] or bad["mismatch"] or bad["extra"]),
            "files": files, "skills": skills}


@router.post("/skills/rehash")
async def skills_rehash():
    """爸爸在宿主改完 D:\\m\\skills 后重扫重建基线（管理员 token 门内）。
    注：图构建时校验的是启动快照——重建后如技能被停用状态未恢复，重启一次即生效。"""
    if not _skills_lock.enabled():
        # d2v03fix3⑨（若若 P1-③必改类）：ok:False+error 并存帧→reason 单键形，
        # 与设置页技能区消费点同批改（W3 起为 SkillsManager.tsx，已改读 j.reason）
        return {"ok": False, "reason": "skills_lock 未启用（设置页先开启）"}
    manifest = _skills_lock.rehash(_SKILLS_DIR)
    return {"ok": True, "count": len(manifest), "note": "基线已重建；若此前技能被停用，重启后生效"}


@router.post("/skills/create")
async def skills_create(req: dict = Body(...)):
    """W3：新建技能 = 建 <name>/SKILL.md（frontmatter name/description + 正文）。
    name 走白名单正则（拒路径穿越）；已存在=拒（改内容请用 /skills/update）。管理员 token 门内。"""
    name = str(req.get("name") or "").strip()
    d = _skill_dir(name)
    if d is None:
        return {"ok": False, "reason": "技能名不合法：只许小写字母/数字/-/_，2-41 位，且首字符为字母或数字"}
    if d.exists():
        return {"ok": False, "reason": f"技能「{name}」已存在（改内容请用编辑）"}
    try:
        d.mkdir(parents=True, exist_ok=False)
        (d / "SKILL.md").write_text(
            _render_skill_md(name, str(req.get("description") or ""), str(req.get("content") or "")),
            encoding="utf-8")
    except Exception as e:
        return {"ok": False, "reason": f"写入失败：{str(e)[:80]}"}
    _token_audit("skills_create", True, name=name)
    return {"ok": True, "name": name, **_after_skill_change(name)}


@router.post("/skills/update")
async def skills_update(req: dict = Body(...)):
    """W3：覆写该技能的 SKILL.md（frontmatter + 正文）。description 缺省时保留原描述。管理员 token 门内。"""
    name = str(req.get("name") or "").strip()
    d = _skill_dir(name)
    if d is None:
        return {"ok": False, "reason": "技能名不合法：只许小写字母/数字/-/_，2-41 位，且首字符为字母或数字"}
    md = d / "SKILL.md"
    if not md.is_file():
        return {"ok": False, "reason": f"技能「{name}」不存在"}
    # r27 评审 P2-7（CB）：SKILL.md 本体若是软链，write_text 会顺链写穿技能目录——拒。
    if md.is_symlink():
        _token_audit("skills_update", False, name=name, reason="SKILL.md 为软链")
        return {"ok": False, "reason": "该技能的 SKILL.md 是符号链接，拒写（防写穿技能目录）"}
    desc = req.get("description")
    if desc is None:
        _, desc, _ = _parse_skill_md(md)
    try:
        md.write_text(_render_skill_md(name, str(desc), str(req.get("content") or "")), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "reason": f"写入失败：{str(e)[:80]}"}
    _token_audit("skills_update", True, name=name)
    return {"ok": True, "name": name, **_after_skill_change(name)}


@router.post("/skills/delete")
async def skills_delete(req: dict = Body(...)):
    """W3：删该技能目录（仅限 _SKILLS_DIR 之下，realpath 前缀双保险）。管理员 token 门内。"""
    name = str(req.get("name") or "").strip()
    d = _skill_dir(name)
    if d is None:
        return {"ok": False, "reason": "技能名不合法：只许小写字母/数字/-/_，2-41 位，且首字符为字母或数字"}
    if not d.is_dir():
        return {"ok": False, "reason": f"技能「{name}」不存在"}
    try:
        shutil.rmtree(d)
    except Exception as e:
        return {"ok": False, "reason": f"删除失败：{str(e)[:80]}"}
    _token_audit("skills_delete", True, name=name)
    return {"ok": True, "name": name, **_after_skill_change(name, removed=True)}


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
                    total[k] += v          # 累加本条增量，不是模型累计值（修 NOVA#2/Cora 用量虚高）
                a["calls"] += 1
                total["calls"] += 1
        except Exception as e:
            # d2v03fix3⑨（若若 P1-③判词缝→本单裁决清）：/usage 全仓零消费
            # （FE 不读、tools 不读——见 grep-closure 豁免账）——error 独存帧改
            # ok:False+reason；异常原文截 80 防泄路径（Veda 形态建议）。
            return {"ok": False, "reason": str(e)[:80]}
    return {"date": today, "by_model": agg, "total": total}


@router.get("/context/threads")
async def context_threads():
    """R53 上下文容量图数据源：usage.jsonl 按线程取最近一次模型调用的 input_tokens。
    基线（系统提示词+工具+技能）取全部记录中的最小 input 估算；差额即对话消息。"""
    f = BASE / "mia_home" / "usage.jsonl"
    # 09-17 批③（Lesson 68）：上下文窗口表进配置页 models.contextLimits（键=模型名 值=窗口），
    # 代码表退为默认值；未知模型兜底窗读 models.contextLimitDefault（默认 131072）。
    from settings_mgr import load_settings
    _m = (load_settings().get("models", {}) or {})
    from settings_schema import default_of as _dof  # 09-17 深夜：默认表单一来源=总表
    LIMITS = dict(_dof("models.contextLimits") or {})
    for _k, _v in (_m.get("contextLimits") or {}).items():
        try:
            LIMITS[str(_k)] = int(_v)
        except (TypeError, ValueError):
            pass
    try:
        _DEF_LIMIT = int(_m.get("contextLimitDefault", _dof("models.contextLimitDefault")) or _dof("models.contextLimitDefault"))
    except (TypeError, ValueError):
        _DEF_LIMIT = 131072  # schema 读取失败时的最后防线
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
            return {"ok": False, "reason": f"context/threads 读取失败: {str(e)[:80]}"}  # d2v03fix3 补漏：Cora265/若若266 实锤 L117（同 L88 型）
    baseline = min(all_inputs) if all_inputs else 0
    out = []
    for t in per.values():
        limit = LIMITS.get(t["model"], _DEF_LIMIT)
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
    return {"status": "ok", "service": "小全车间", "agent": "xiaoquan"}


@router.post("/approvals")
async def api_approve(req: dict = Body(...), request: Request = None):
    """R69 确认门 v2（Eve A1）：爸爸的外部批准——与模型重试不可辨的问题在此解耦：
    批准只认【模型之外】的来源。本机 curl / 汇报卡按钮 → 该线程该工具下一次调用放行一次。
    R10.3（NOVA 🟡A 时窗调包）：请求须带拦截消息里的指纹 fp——与登记不符=拒（"参数已变"），
    绝不静默重绑最新被拦的那条；无登记=拒（不覆盖已有批准，防误点/连点杀死有效批准）。
    R10.12（爸爸裁决）：X-By: admin 作废——常数头零熵（R69 时代无统一 token 的遗产），
    真锁=中间件 api_token_guard（/approvals 全程 token fail-closed），拆假锁不再给人双保险错觉。"""
    import approvals as _ap
    tid, tool = str(req.get("thread_id", "")), str(req.get("tool", ""))
    if not tid or not tool:
        # v0.3 件三：失败键统一 ok:False+reason（与 api_reset_thread 对齐；前端只读 ok，
        # 全仓 grep 无按 error 键解析的消费方——ToolCallBox.tsx/verify/test 均零染指）
        return {"ok": False, "reason": "需要 thread_id 与 tool"}
    ok, why = _ap.approve(tid, tool, str(req.get("fp") or ""))
    _token_audit("approval_granted" if ok else "approval_denied", ok,
                 tool=tool, tid=tid[:8],
                 ip=(request.client.host if request and request.client else "?"),
                 why=why)  # R10.5（NOVA 遗留）：批准动作带来源标注入审计
    # r25（军事链最后一公里）：批准成功=立即下推唤醒被拦线程重试——
    # 部门/总管 run 停在拦截处无人推进；主对话同理（点完批准不用再喊"继续"）。
    # 进程内 SDK（X-Internal-Key=同进程钥匙），fire-and-forget 不阻塞响应。
    if ok:
        import threading as _th
        def _nudge(_tid=tid):
            try:
                # r27（发现#12 实锤）：旧版用 get_sync_client+127.0.0.1 被 R80 纵深 403——
                # "批准即唤醒"一直空转且被 pass 吞掉。改用与 webhook 汇报同构的 _sdk_client()
                # （async get_client+localhost+X-Internal-Key），失败记审计不再静默。
                import asyncio
                from . import tasks as _tk
                _sdk = _tk._sdk_client
                async def _push():
                    c = _sdk()
                    th = await c.threads.get(_tid)
                    aid = th.get("assistant_id") or "agent"
                    await c.runs.create(_tid, aid,
                        input={"messages": [{"role": "user", "content":
                            "你被批准的那一步已通过（指纹已核对）。原样重试被拦的调用，继续完成任务；"
                            "完成后按你的角色汇报（调度层汇总上报，主对话直接呈报管理员）。",
                            # r44b（hy4 P1-5）：nudge=系统注入消息，gate 换任务判定
                            # 必须排除它（否则一次批准=软告警清零一次，语义被捅穿）
                            "additional_kwargs": {"system_nudge": True}}]},
                        config={"configurable": {"user_id": "approve-nudge"}})
                asyncio.run(_push())
            except Exception as e:
                _token_audit("approval_nudge_fail", False, tool=tool, tid=tid[:8],
                             why=f"{type(e).__name__}: {str(e)[:120]}")
        _th.Thread(target=_nudge, daemon=True).start()
    return {"ok": ok, "reason": why, "approved": f"{tid[:8]}…:{tool}" if ok else ""}


@router.delete("/approvals")
async def api_revoke(req: dict = Body(...), request: Request = None):
    """R10.3（NOVA ⚪E）：撤销未消费的批准/拦截登记——误点有后悔药，不再悬 24h 等米娅兑现。
    r25：X-By 同 approve 作废，门=token（中间件）。"""
    import approvals as _ap
    tid, tool = str(req.get("thread_id", "")), str(req.get("tool", ""))
    if not tid or not tool:
        # v0.3 件三：失败键统一（同 api_approve，两分支同形同注释口径）
        return {"ok": False, "reason": "需要 thread_id 与 tool"}
    return {"ok": _ap.revoke(tid, tool)}


@router.post("/approvals/reset")
async def api_reset_budget(req: dict = Body(...), request: Request = None):
    """r41（hy4 P1-2 补的口子）：重置该线程的网关批准卡预算——预算拒信里告诉爸爸
    "可在管理端重置本任务预算"，落点就是这里（token 门内）。"""
    import approvals as _ap
    tid = str(req.get("thread_id", ""))
    if not tid:
        # v0.3 件三：原返回 {"error":...} 连 ok 键都没有（前端接线前必须一字面）——
        # 统一为 ok:False+reason（与另两门同形）
        return {"ok": False, "reason": "需要 thread_id"}
    n = _ap.reset_task_cards(tid)
    _token_audit("approval_budget_reset", True, tid=tid[:8], cleared=n)
    return {"ok": True, "cleared_cards": n}


@router.post("/approvals/guard_unlock")
async def api_guard_unlock(req: dict = Body(...), request: Request = None):
    """r61b（hy4 P1-1 闭环）：爸爸接管后手动提前解冻线程。r61j N-4：退避真值
    30min→1h→2h→第 3 次永久（永久锁只能走本端点），解冻动作收进门侧单一真源
    ConfirmGateC1.guard_unlock（三集合同清 lock/streak/frozen_hold——端点旧自 pop
    漏清 hold，解封后 wrap 会误吃一次接力拒信，r61h 九轮 hy4 N-4 点的名）。
    {thread_id?}——不传=解全部。token 门内（/approvals 前缀）。
    r61k：返回 ok=bool(cleared)——cleared=0（无匹配线程/门不在此进程）时
    ok:false+hint，不再静默 ok:true。
    d2v03fix3⑤ 命名债：hint 键退役改 reason（全仓 grep 消费方=m-gates 绊线一格+
    本端点自产帧，前端零读此键——三处同批改，error 键绝迹口径不变）。"""
    import approvals as _ap
    from mia_agent.confirm_gate_c1 import ConfirmGateC1
    tid = str(req.get("thread_id", ""))
    cleared = ConfirmGateC1.guard_unlock(tid)
    _ap._audit("guard_unlock", thread_id=tid or "*", by="admin", cleared=cleared)
    _token_audit("approval_guard_unlock", bool(cleared), tid=tid[:8] or "*", cleared=cleared)
    # r61k 第二笔（hy4 十轮端点侧点1）：cleared=0 不再静默 ok:true——跨进程部署/
    # tid 拼错/花名册空三种情况下，审计账会说"爸爸解冻了"而门根本没动（静默失败=
    # 双倍失败）。ok 必须跟 cleared 走；0 时给 reason 指排查方向。token 账同口径。
    # d2v03fix3⑤：键名 hint→reason（与其余失败帧统一键形）。
    if not cleared:
        return {"ok": False, "cleared": 0,
                "reason": "无匹配线程或门实例不在此进程（跨进程/tid 拼错/花名册空）"}
    return {"ok": True, "cleared": cleared}


@router.post("/approvals/reset_thread")
async def api_reset_thread(req: dict = Body(...), request: Request = None):
    """D2 挂账四件④（hy4 十二轮 P-B，09-15 爸爸令动工）：管理端"重置本线程状态"=
    三锁叠加（冻结+超预算+压力钉）的唯一总出口。guard_unlock 只开冻结那把，
    三把齐扣时批准卡路径走不到=线程死锁。本端点一次清三锁并落账 desk_state_reset
    （P-B 明令必须落账），卡片配额同步走 reset_task_cards（与 /approvals/reset 同源）。
    {thread_id} 必填真值（? 桶不连坐）。token 门内（/approvals 前缀）。
    v0.3 件二：请求体可选 force=true=审计链旁路（先清锁后落账，落账失败走死信
    文件）——二次确认就是这一个字段（无 settings 键，L26 不破；前端两步式后置）。"""
    import approvals as _ap
    from mia_agent.confirm_gate_c1 import ConfirmGateC1
    tid = str(req.get("thread_id", ""))
    if not tid:
        # hy4 十五轮②：空 tid 失败键与下方 reset 失败分支统一为 reason（前端接线前必须一字面）
        # v0.3 件四：失败也是安全事件——"有声"家规补落一条失败账（此前此分支零账静默，
        # 空请求打门审计面上什么都不发生；tid 记 "*" 与成功账同形，reason 固定短语供机判）
        _token_audit("approval_reset_thread", False, tid="*", reason="missing_thread_id")
        return {"ok": False, "reason": "需要 thread_id（真值，? 桶不连坐）"}
    r = ConfirmGateC1.reset_thread(tid, force=bool(req.get("force")))
    if not r.get("ok"):
        # hy4 十五轮③(b)：失败也是安全相关事件（落账失败=三锁未清需人工）——补落一条
        # 失败账，零账不符"有声"家规；参数与成功账同名（tid/reason）。
        _token_audit("approval_reset_thread", False, tid=tid[:8], reason=r.get("reason", ""))
        return {"ok": False, "reason": r.get("reason", "")}
    cards = 0
    try:
        cards = _ap.reset_task_cards(tid)
    except Exception:
        pass  # 配额清失败不回滚三锁（门账已落，配额是软约束）
    if r.get("audit") == "deadletter":
        # v0.3 件二死信帧（十六轮三改）：force 路任一环节失败都汇到此帧（出口优先），
        # desk_state_reset 账搬家到 mia_home/runtime/bypass_deadletter.jsonl——行内
        # stage/cleared 区分"锁已清只缺账"与"清锁抛、锁可能半清"，清前三锁计数与
        # 异常名也在那行。token 账不带 freeze/budget/pressure：返回帧没有这些键，
        # 塞零=假账比缺账更坏。
        _token_audit("approval_reset_thread", True, tid=tid[:8], forced=True,
                     audit="deadletter", cards=cards)
        return {"ok": True, "forced": True, "audit": "deadletter", "cards": cards}
    _flag = {"forced": True} if r.get("forced") else {}  # v0.3 件二：force 帧账注（普通帧账形零变化）
    # hy4 十五轮③(a) 账注：budget=两表命中数之和非线程数，多实例按实例累加
    _token_audit("approval_reset_thread", True, tid=tid[:8],
                 freeze=r["freeze"], budget=r["budget"], pressure=r["pressure"],
                 cards=cards, **_flag)
    # hy4 十四轮 §⑤连带：budget 是两表命中数之和（单实例最多 2），明细 budget_detail
    # 原样透传给前端（token 账参数不变——账口径漂移比少一个字段更坏）。
    return {"ok": True, "freeze": r["freeze"], "budget": r["budget"],
            "budget_detail": r.get("budget_detail"),
            "pressure": r["pressure"], "cards": cards, **_flag}


# ── R2.1（2026-08-29 知夏）：旧配置系统已删除 ──
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


# ── r49 双钮"批准并记住这类"（爸爸 09-13 拍板；护栏=精确键/设置页可删/命中全审计/米娅无权）──
# 路径故意不放 /settings/ 下——/settings/{section} 通配会吞掉精确路由（token 教训同款），
# 独立前缀 /remember-rules（app.py 两侧守卫列表已同步加门）。

@router.get("/remember-rules")
async def remember_rules_list():
    from settings_mgr import load_settings
    return {"rules": (load_settings().get("remember_rules") or [])}


@router.post("/remember-rules")
async def remember_rules_add(req: dict = Body(...)):
    """批量卡"批准并记住"钮回调：存精确规则 (tool, key)。key 由 args 规范化提取，
    提取不到（空 key）=拒绝——永不支持通配/全工具放行。"""
    from settings_mgr import load_settings, SETTINGS_PATH
    import json as _json
    from mia_agent.remember_rules import rule_key
    tool = str(req.get("tool") or "")
    key = rule_key(tool, req.get("args") or {})
    if not key:
        # d2v03fix3⑨（若若 P1-③必改类）：并存 error 键改 reason——本端点前端
        # （BatchApprovalInterrupt.tsx:124）POST 后响应体整体忽略，零消费直改无连带。
        return {"ok": False, "reason": "该调用提取不到精确键（不接受通配规则）"}
    s = load_settings()
    rules = s.setdefault("remember_rules", [])
    if any(str(r.get("key", "")).lower() == key for r in rules):
        return {"ok": True, "key": key, "note": "规则已存在"}
    rules.append({"key": key, "tool": tool,
                  "note": str(req.get("note") or "")[:80],
                  "created": str(req.get("created") or "")})
    SETTINGS_PATH.write_text(_json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    _token_audit("remember_rule_add", True, tool=tool, key=key[:60])
    return {"ok": True, "key": key}


@router.delete("/remember-rules")
async def remember_rules_del(req: dict = Body(...)):
    from settings_mgr import load_settings, SETTINGS_PATH
    import json as _json
    key = str(req.get("key") or "").lower()
    s = load_settings()
    rules = s.get("remember_rules") or []
    kept = [r for r in rules if str(r.get("key", "")).lower() != key]
    s["remember_rules"] = kept
    SETTINGS_PATH.write_text(_json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    _token_audit("remember_rule_del", True, key=key[:60], removed=len(rules) - len(kept))
    return {"ok": True, "remaining": len(kept)}


# ── r51 reflect 做梦作业（记忆升级 plan-memory；夜间 n8n 调用）──
# 痛点实锤：facts-2026-09.md 4224 行里混着抽取事故（思维链整段入库）。
# 流程：备份先行 → 规则预筛（机械判思维链/超长行）→ LLM 合并去重 → 写回+统计。
# 幂等：每日只跑一次（.reflect_last 记日期）；写坏可从 backup 回滚。

@router.post("/memory/reflect")
async def memory_reflect():
    import json as _json
    import re as _re
    import time as _t
    from pathlib import Path as _P
    from providers import make_model
    from settings_mgr import load_agents_config

    mem = _P(BASE) / "mia_home" / "memory"
    today = _t.strftime("%Y-%m")
    facts_file = mem / f"facts-{today}.md"
    if not facts_file.exists():
        return {"ok": True, "note": "本月无 facts 文件，无梦可做"}
    stamp = _t.strftime("%Y%m%d")
    last_f = mem / ".reflect_last"
    if last_f.exists() and last_f.read_text(encoding="utf-8").strip() == stamp:
        return {"ok": True, "note": "今日已 reflect（幂等跳过）"}

    lines = [ln.rstrip("\n") for ln in facts_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # 规则预筛：思维链/日志事故行机械判（比 LLM 便宜且稳）
    _TRASH_PAT = _re.compile(
        r"(Analyze the Request|Thinking Process|ModelResponse|prompt_tokens|"
        r"^\s*\d+\.\s+\*\*(Analyze|Evaluate|Content|Task|Context)|Tool call:|Metadata:)", _re.I)
    keep, trash = [], []
    for ln in lines:
        (trash if (_TRASH_PAT.search(ln) or len(ln) > 150) else keep).append(ln)

    # ── r55 证据评分三坑修（五家提案全收）──
    # 基数去重（Eve"次数会骗人，基数不会"）：同事实按 distinct 日期计数
    _ANXIETY_PAT = _re.compile(r"(吗|没有|呢|？|\?)")   # Cora 焦虑分流：问句/待办不升 importance
    _AUTH_PAT = _re.compile(r"(爸爸(说|定|教|要求|拍板)|铁律|红线)")  # NOVA 权威直通：一次话一级重要
    date_seen = {}   # {归一化事实: set(日期)}
    for ln in keep:
        mm = _re.match(r"-\s*\[(\d{2}-\d{2})\]\s*(.+)", ln)
        if mm:
            date_seen.setdefault(mm.group(2).strip()[:60], set()).add(mm.group(1))
    promoted, nag, plain = [], [], []
    for ln in keep:
        mm = _re.match(r"-\s*\[(\d{2}-\d{2})\]\s*(.+)", ln)
        body = mm.group(2).strip() if mm else ln[2:].strip()
        seen_days = len(date_seen.get(body[:60], set()))
        if _ANXIETY_PAT.search(body):
            nag.append(ln)            # 焦虑型：催办清单，不进 importance 升级（防记忆库被未解决问题污染）
        elif _AUTH_PAT.search(body):
            promoted.append(ln)       # 权威直通：不看 seen
        elif seen_days >= 2:
            promoted.append(ln)       # 基数升级：跨≥2天重现=真验证
        else:
            plain.append(ln)
    # LLM 合并去重（keep 行批 60 行一次，防超上下文）
    merged = []
    _ac = load_agents_config()
    _fc = _ac.get("archivist") or _ac.get("scribe") or _ac.get("boss") or {}
    m = make_model(_fc.get("provider", ""), _fc.get("model", ""))
    worklist = promoted + plain
    for i in range(0, len(worklist), 60):
        batch = worklist[i:i + 60]
        prompt = (
            "下面是智能体记忆库的候选事实清单。带 ★ 前缀的是已判定值得长期保留的"
            "（权威原话或跨天重现），合并时务必保留并加 ★ 前缀。\n"
            "请合并去重：同一主题多条合并成一条（保留最早的日期标记），删除过时或无信息量的条目，"
            "输出清洗后的完整清单。\n"
            "格式：每行 `- [MM-DD] 事实`（重要条目前加 ★）。只输出清单本身，不要解释。\n\n"
            + "\n".join(("★ " + x if x in promoted else x) for x in batch))
        r = m.invoke(prompt)
        txt = str(getattr(r, "content", "")).strip()
        for ln in txt.splitlines():
            ln = ln.strip()
            if ln.startswith("- ") and 8 < len(ln) <= 150:
                merged.append(ln)
    # 催办清单独立落盘（不混进事实库——Cora 坑1）
    if nag:
        (mem / f"nag-{today}.md").write_text("\n".join(nag) + "\n", encoding="utf-8")
    # preview_mode（Cora 坑2：夜间自动改记忆=睡着时改，首夜只预览不动库）
    preview_f = mem / ".reflect_preview"
    if preview_f.exists():
        (mem / f"reflect-preview-{stamp}.md").write_text(
            "\n".join(merged) + "\n\n## 催办（未升 importance）\n" + "\n".join(nag), encoding="utf-8")
        preview_f.unlink()  # 预览一晚，下一夜放开
        return {"ok": True, "preview": True, "promoted": len(promoted),
                "nag": len(nag), "note": "预览模式：结果已落 reflect-preview 文件，未动库"}
    # 备份先行 → 写回
    backup = mem / f"facts-{today}-backup-{stamp}.md"
    backup.write_text(facts_file.read_text(encoding="utf-8"), encoding="utf-8")
    facts_file.write_text("\n".join(merged) + "\n", encoding="utf-8")
    last_f.write_text(stamp, encoding="utf-8")
    _token_audit("memory_reflect", True, keep=len(keep), trash=len(trash),
                 merged=len(merged), total=len(lines))
    return {"ok": True, "total": len(lines), "rule_trash": len(trash),
            "kept": len(keep), "merged": len(merged),
            "backup": backup.name}


def _reflect_nightly_daemon():
    """r51b（爸爸 10:3x 指正）：凌晨定时是纸上谈兵——机器未必开着。
    改双条件触发，每 30 分钟自检一次（幂等由 .reflect_last 日期戳兜底）：
    ① 在线 ≥4 小时 且 距上次 reflect ≥12 小时（开机常态：上午开机，下午整理）
    ② facts 累计 ≥800 行 且 距上次 ≥6 小时（写爆了就清，不等时长）
    失败只 print，绝不影响主服务。"""
    import asyncio
    import time as _t2
    from pathlib import Path as _P2

    boot = _t2.time()

    def _last_ts() -> float:
        f = _P2(BASE) / "mia_home" / "memory" / ".reflect_last"
        try:
            d = f.read_text(encoding="utf-8").strip()  # YYYYMMDD
            return _t2.mktime(_t2.strptime(d, "%Y%m%d")) if d else 0.0
        except Exception:
            return 0.0

    def _facts_lines() -> int:
        f = _P2(BASE) / "mia_home" / "memory" / f"facts-{_t2.strftime('%Y-%m')}.md"
        try:
            return sum(1 for _ in f.open(encoding="utf-8"))
        except Exception:
            return 0

    def _loop():
        while True:
            _t2.sleep(1800)  # 30 分钟自检
            try:
                up_h = (_t2.time() - boot) / 3600
                since_h = (_t2.time() - _last_ts()) / 3600
                lines = _facts_lines()
                cond_a = up_h >= 4 and since_h >= 12
                cond_b = lines >= 800 and since_h >= 6
                if not (cond_a or cond_b):
                    continue
                r = asyncio.run(memory_reflect())
                print(f"[reflect] 触发（在线{up_h:.1f}h/距上次{since_h:.1f}h/{lines}行）：{r}", flush=True)
            except Exception as e:
                print(f"[reflect] 整理失败（下轮再战）：{type(e).__name__}: {e}", flush=True)

    threading.Thread(target=_loop, daemon=True, name="reflect-nightly").start()


threading.Thread(target=_reflect_nightly_daemon, daemon=True, name="reflect-kick").start()
