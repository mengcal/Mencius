"""R69 确认门 v2：外部批准登记处（Eve A1 方向）。
软门的"重试放行一次"分不清是爸爸同意还是模型硬磨；本模块提供【模型之外】的批准通道：
office /approvals（爸爸点/敲）→ 该线程该工具的下一次调用直接放行（一次性，消费即焚）。

R73（Cora P3）：批准登记带时间戳，消费时超 24 小时=作废——今天批的动作不会下月还悬着。
R10.2（hy4 ①-1/①-4 审计）：**参数级绑定下沉到本模块**——
  · set_blocked：门拦截时登记"被拦那次的参数指纹"（全局共享，主图/子图同一张表，封跨实例锚点分裂）；
  · approve：爸爸批准=对"被拦的那次具体调用"开绿灯，指纹随批准固化；
  · consume(tid, tool, fp)：参数指纹一致才放行；**不一致=批准当场作废**（不退回、不续期）——
    封掉"批无害→换恶意参数→多挨一次拦就通行"的无限批准链（空白支票攻击）。
R10.3（NOVA 🟡A/⚪E + Lyra 请验2）：
  · approve 带 fp 校验：爸爸批准的必须是【他屏幕上看到的那条拦截】——按钮把消息里的指纹带回，
    与登记指纹不符=拒绝（"参数已变，请看最新拦截消息重新决定"），不静默重绑最新一条；
    防时窗调包：米娅在爸爸读消息与点按钮之间换参数重拦，旧按钮打不中新锚点。
  · approve 无登记指纹=拒批（不再绑 None 覆盖已有批准）——误点/连点不再杀死爸爸刚批的有效批准；
  · revoke：未消费批准可撤销（误点后悔药），不再悬 24h。
r26（I1 并发实测实锤）：登记键从 (thread,tool) 升级为 (thread,tool,fp)——
米娅**同一轮并发发多条同名工具调用**（如三条不同 curl 探测）时，旧单槽结构
后拦的覆盖先拦的，爸爸只能批到最后一条，其余"批了也不生效"。多槽并行登记、
逐条独立批准/消费/撤销，fp 语义不变。"""
import threading
import time

_lock = threading.Lock()
_approved: dict = {}    # {(thread_id, tool, fp): (approved_ts, used)} —— 已批准待消费
_blocked_fp: dict = {}  # {(thread_id, tool, fp): blocked_ts} —— 被拦待批的调用（每条独立）
_TTL_SEC = 24 * 3600

# ── r49 台账批·批准账（两本账之二）：爸爸权柄记录落盘 ──
# 观测账=flow_obs（米娅动作）；批准账=本件（卡弹出/批准/兑现/撤销/回血/reset 全事件）。
# append-only jsonl，与观测账同目录（数据区 notes/，米娅可 grep——她的账她也有权看）；
# 失败 print 出声不挡路。低频事件（每日几十条）单文件足够。
import json as _json
import os as _os
import uuid as _uuid
_audit_lock = threading.RLock()  # r61b：可重入——external_store 需"持锁判定+经 _audit 落账"原子化（P1-8）
_AUDIT_PATH = None  # 首次 _audit 时惰性初始化（模块被 office 与 agent 两侧 import，路径以 agent 侧为准）


def _audit_path():
    global _AUDIT_PATH
    if _AUDIT_PATH is None:        _AUDIT_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                    "mia_home", "notes", "approvals_log.jsonl")
    return _AUDIT_PATH


def _audit(ev: str, thread_id: str = "", tool: str = "", fp: str = "", **kw) -> None:
    try:
        # r61（NOVA P0-3 撞库量化案）：tid 全长存储不再截 8 位——
        # 16.7 分钟窗口确定性碰撞会静默串单，账本可读性让位于正确性
        rec = {"ts": round(time.time(), 1), "ev": ev,
               "tid": str(thread_id or ""), "tool": tool, "fp": fp}
        rec.update(kw)
        line = _json.dumps(rec, ensure_ascii=False)
        with _audit_lock:
            with open(_audit_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"[approvals] 批准账落盘失败（不挡路）：{e}", flush=True)


# ── r58 对外派活：外部岗回调结果**并入批准账 jsonl**（ev=external_result，
#    零新路径操作——复用 _audit 既有写通道；岗名进账走 json.dumps 转义+40 字截断，
#    注入面由"字段永不被解析执行"兜底——r61e Cora N5：旧注释曾虚称"sha 化"，
#    承诺与实现对齐：如实说转义，不装哈希；米娅 grep 可查）──
#    架构定案（r58b）：**平台永不外连**（外部岗=本机环回也过不了 Mimosa SSRF 纪律，
#    且反转更优）——派活写 ev=external_dispatch 待办，外部岗轮询取单、跑完回调。
def _audit_tail_scan(pred, tail_bytes: int = 0):
    """倒序找第一条满足 pred 的记录。
    r61c N9（hy4 二轮）：superseded/归属判定要的是**全历史存在性**，尾窗语义会把
    "派单早、回调晚"的合法单误拒（账一大即自伤，单调恶化）——external 事件量小，
    默认全量倒序读（tail_bytes=0）；尾窗只留给"最近一条"语义的将来用法。
    账过 10MB 时改 external_* 独立 jsonl（挂账二期）。"""
    path = _audit_path()
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - tail_bytes) if tail_bytes else 0)
            if tail_bytes and size > tail_bytes:
                f.readline()  # 丢弃可能残缺的首行
            data = f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    for ln in reversed(data.splitlines()):
        try:
            r = _json.loads(ln)
        except Exception:
            continue
        if pred(r):
            return r
    return None


def _f0(v):
    """r61c N17：ts 安全 float 化（脏值回 0，不炸读账）。"""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def external_store(post_name: str, result: dict, task_id: str = "") -> bool:
    """入站消毒（r61 NOVA P1-2/Veda B-P0）：外部回传先过机器门内容规则，
    high 命中→隔离（quarantined，不入正文）；全部打 external_artifact 标
    （米娅读到即知是不可信外部文本，按中立文本纪律处理）。
    r61b（hy4 P1-7/P1-17）：task_id 必传（缺键碰撞=静默吞结果的 superseded 误标）；
    result 落账截 8KB（回调 body 无上限=账文件 DoS）。"""
    if not task_id:
        return False  # 调用方（router）拒收 400——同岗多结果共键碰撞不可接受
    digest = task_id
    marked = dict(result) if isinstance(result, dict) else {"data": result}
    marked["external_artifact"] = True
    # r61c N4（hy4）：先**全文**过门再截断落账——旧版先截 8KB 后扫，回执 6000 字
    # 之外藏私钥/强删=免检入库（消毒面被自家截断捅穿）。
    try:
        from mia_agent.guard_scan import scan_tool, rule_ids
        g = scan_tool("write_file", {"file_path": "external/incoming.md",
                                     "content": _json.dumps(marked, ensure_ascii=False)})
        if g["level"] == "high":
            marked = {"quarantined": True, "rids": rule_ids(g["findings"][:3]),
                      "post": post_name}
    except Exception:
        pass
    marked = {k: (v[:8000] if isinstance(v, str) and len(v) > 8000 else v)
              for k, v in marked.items()}
    # r61d P2-4（hy4）：只截 str 值的话，嵌套 dict/list 不受 8KB 约束——总预算兜底
    _dumped = _json.dumps(marked, ensure_ascii=False)
    if len(_dumped) > 16000:
        marked = {"oversized_truncated": True, "post": post_name, "head": _dumped[:8000]}
    # r61（Eve 审点①）+r61b P1-8：done 幂等判定与落账**同持一把锁**——
    # 并发双回调互不看见=两条都 done 都不标 superseded 的洞就此关闭。
    with _audit_lock:
        if marked.get("done"):
            hit = _audit_tail_scan(
                lambda r: (r.get("ev") == "external_result" and r.get("tid") == digest
                           and (r.get("result") or {}).get("done")))
            if hit is not None:
                marked["superseded"] = True
        _audit("external_result", thread_id=digest, tool=str(post_name)[:40], result=marked)
    return True


def external_task_ctx(post_name: str, task_id: str) -> dict:
    """r61e（Lyra②nonce+Veda②+Cora N6）：回调校验三件套的数据源——
    返回 {"known": 派给本岗?, "claimed": 本岗领过?, "nonce": 一次性凭证}。
    nonce 由派活时生成、账尾取回；回调必须原样带回（伪造 done 需同时有子钥+nonce+已领取，
    验收欺骗链断在"未领取的单不可能有回执"上）。"""
    ctx = {"known": False, "claimed": False, "nonce": ""}
    hit = _audit_tail_scan(lambda r: (r.get("ev") == "external_dispatch"
                                      and r.get("tid") == task_id
                                      and r.get("tool") == str(post_name)[:40]))
    if hit is None:
        return ctx
    ctx["known"] = True
    ctx["nonce"] = str(hit.get("nonce") or "")
    chit = _audit_tail_scan(lambda r: (r.get("ev") == "external_claim"
                                       and r.get("tid") == task_id
                                       and r.get("tool") == str(post_name)[:40]))
    ctx["claimed"] = chit is not None
    return ctx


def external_tid_owned(post_name: str, task_id: str) -> bool:
    """r61b P2-4：回调的 task_id 必须是派给**本岗**的单（账尾找 dispatch 记录）——
    持子钥给任意 tid 伪造 done 的路封死。"""
    return external_task_ctx(post_name, task_id)["known"]


def external_dispatch(post_name: str, task: str) -> str:
    """派活=落一条待办账（外部岗轮询取走）。返回派活 id（取单/领取/结果三账串链）。
    r61：任务文本先过机器门（Veda/NOVA 出站注入面——派活动作人环批过≠文本逐字可信）。"""
    # r61（Eve 审点②）：did 用 uuid4——旧时间戳+pid 尾是"侥幸正确"（靠单调性
    # 碰巧不撞），唯一性要从碰巧变设计，一行的事。
    did = "d" + _uuid.uuid4().hex[:12]
    nonce = _uuid.uuid4().hex[:8]  # r61e Lyra②：一次性回调凭证（不依赖网络拓扑的身份）
    try:
        from mia_agent.guard_scan import scan_tool, rule_ids
        g = scan_tool("execute", {"command": task})
        if g["level"] == "high":
            _audit("external_dispatch_blocked", thread_id=did, tool=str(post_name)[:40],
                   rids=rule_ids(g["findings"][:3]))  # r61e Cora N4：拒账也脱敏存规则 ID
            return ""  # 调用方见空串即知被机器门拒派
    except Exception:
        pass
    _audit("external_dispatch", thread_id=did, tool=str(post_name)[:40],
           task=str(task)[:2000], nonce=nonce)
    return did


def external_pending_view(post_name: str, limit: int = 3, claim_timeout_s: int | None = None) -> list:
    # 09-17 批⑤（Lesson 68）：领取超时进配置页 approvals.claimTimeout（秒，默认 1800=30 分钟惯例值）
    if claim_timeout_s is None:
        try:
            from settings_mgr import load_settings
            claim_timeout_s = int((load_settings().get("approvals", {}) or {}).get("claimTimeout", 1800) or 1800)
        except Exception:
            claim_timeout_s = 1800
    """取单预览（r61 NOVA P0-4：纯读零副作用——监控探测不饿死真岗）。
    可领=未 done、未 in-flight（领取后 30 分钟无回执视为岗挂）、退单<3 次。"""
    out = []
    try:
        with open(_audit_path(), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    now = time.time()
    state = {}
    for ln in lines:
        try:
            rec = _json.loads(ln)
        except Exception:
            continue
        ev, tool = rec.get("ev"), rec.get("tool")
        tid = rec.get("tid", "")
        if not tid:
            continue  # r61b 冒烟逮到的僵尸单：早期无 did 时代的空 tid dispatch
            # 永远可领永远领不走，卡住每个上岗者——账只追加不删，展示层过滤。
        if ev == "external_dispatch" and tool == post_name:
            state[tid] = {"dispatch_ts": _f0(rec.get("ts")), "claim_ts": 0,
                          "task": rec.get("task", ""), "done": False, "rejects": 0,
                          "nonce": str(rec.get("nonce") or "")}
        elif ev == "external_claim" and tool == post_name and tid in state:
            # r61b P1-6/r61c N17：ts float 化且兜异常——脏账一条坏 ts 不该炸 500
            state[tid]["claim_ts"] = max(state[tid]["claim_ts"], _f0(rec.get("ts")))
        elif ev == "external_result" and tool == post_name and tid in state:
            res = rec.get("result") or {}
            if res.get("done"):
                state[tid]["done"] = True
            elif res.get("reject"):
                # r61b P1-16（hy4 命门）：旧版"非 done 即退单"把**进度上报**当退单，
                # 且重放 3 次进度包=任务永久下线。退单必须显式 reject 标记才计数。
                state[tid]["claim_ts"] = 0
                state[tid]["rejects"] = state[tid].get("rejects", 0) + 1
            # 其余（纯进度/备注）：不动状态——in-flight 靠超时兜底
    for tid in sorted(state, key=lambda k: -state[k]["dispatch_ts"]):
        s = state[tid]
        if s["done"] or s.get("rejects", 0) >= 3:
            continue
        if s["claim_ts"] and (now - s["claim_ts"]) < claim_timeout_s:
            continue
        if len(out) >= limit:
            break
        out.append({"id": tid, "task": s["task"], "rejects": s.get("rejects", 0),
                    "nonce": s.get("nonce", "")})  # r61e Lyra②：岗回执必须原样带回
    return out


def external_claim(post_name: str, task_id: str) -> bool:
    """显式领取（POST /external/claim，与预览分离——GET 不写账）。
    r61b P1-4（hy4）：**条件化领取**——复核该单此刻仍可领（未 done/未在飞/退单<3）
    才落 claim 账；持锁"复核+落账"原子，双岗并发领同单只有一个 True。"""
    with _audit_lock:
        if not any(t["id"] == task_id for t in
                   external_pending_view(post_name, limit=10**9)):  # r61c N18：全量复核
            return False
        _audit("external_claim", thread_id=task_id, tool=str(post_name)[:40])  # N19 键形统一
        return True


def external_recent(limit: int = 10) -> list:
    """米娅抽检核验用：最近 N 条外部回传（新→旧，读批准账过滤）。"""
    out = []
    try:
        with open(_audit_path(), "r", encoding="utf-8") as f:
            for ln in f.read().splitlines()[::-1]:
                try:
                    rec = _json.loads(ln)
                except Exception:
                    continue
                if rec.get("ev") == "external_result":
                    out.append(rec)
                    if len(out) >= max(1, min(int(limit), 50)):
                        break
    except FileNotFoundError:
        pass
    return out
# r27（发现#11 双唤醒竞争实锤：approve 自带 nudge 唤醒重试，用户/前端的第二条唤醒消息
# 会打断第一个 run——旧"消费即焚"让批准烧在未完成的 run 里，同参数再试反被拦）。
# 修法语义：批准后 90 秒"重试竞争窗"内同一 fp 最多放行 3 次（同参数=爸爸批的就是这件事，
# 不构成空白支票）；窗后回到一次性。换参数=不同 fp=仍须重新请示，原防线不动。
_RETRY_WINDOW_SEC = 90
_RETRY_MAX = 3


def set_blocked(thread_id: str, tool: str, fp: str) -> None:
    """门拦截时登记本次调用指纹（approve 时消费，成为批准的绑定对象）。同键重复拦截=刷新时间戳。"""
    with _lock:
        _blocked_fp[(thread_id, tool, fp)] = time.time()
        if len(_blocked_fp) > 400:  # R10.3（Eve P3）裁剪兜底：按时间戳清最老一半
            cutoff = sorted(_blocked_fp.values())[len(_blocked_fp) // 2]
            for k in [k for k, ts in list(_blocked_fp.items()) if ts <= cutoff]:
                _blocked_fp.pop(k, None)
    _audit("blocked", thread_id, tool, fp)


def approve(thread_id: str, tool: str, fp: str) -> tuple[bool, str]:
    """批准绑定"被拦那次调用的指纹"（多槽版：同线程同工具的不同参数各自可批）。
    R10.3：fp 必须与登记一致（爸爸批的是他看到的那条）；无登记=无批对象，一律拒。
    R10.4：fp 必填。返回 (ok, 理由)。"""
    with _lock:
        if not fp:
            return False, "缺少指纹 fp——请从拦截消息里的〔fp:…〕原样复制（批准与参数绑定）"
        key = (thread_id, tool, fp)
        ts = _blocked_fp.pop(key, None)
        if ts is None:
            # 区分"这个工具压根没被拦"与"fp 对不上（参数已变/已被批过）"
            any_pending = any(k[0] == thread_id and k[1] == tool for k in _blocked_fp)
            if any_pending:
                return False, "参数已变——请看最新一条拦截消息上的指纹，重新决定再批"
            return False, "没有待批准的拦截记录（可能已被消费/过期，或工具名不匹配）"
        if time.time() - ts > _TTL_SEC:
            return False, "该拦截登记已超过 24 小时作废——请重新发起"
        _approved[(thread_id, tool, fp)] = (time.time(), 0)  # r27: (批准时刻, 已放行次数)
        if len(_approved) > 500:  # 慢泄漏兜底：超量清掉最老一半
            cutoff = sorted(v[0] for v in _approved.values())[len(_approved) // 2]
            for k, v2 in list(_approved.items()):
                if v2[0] <= cutoff:
                    _approved.pop(k, None)
    _audit("approved", thread_id, tool, fp)
    return True, "ok"


def revoke(thread_id: str, tool: str) -> bool:
    """R10.3（NOVA ⚪E）：撤销该线程该工具的全部未消费批准/拦截登记（误点后悔药）。"""
    with _lock:
        ks = [k for k in _approved if k[0] == thread_id and k[1] == tool]
        ks += [k for k in _blocked_fp if k[0] == thread_id and k[1] == tool]
        for k in ks:
            _approved.pop(k, None)
            _blocked_fp.pop(k, None)
    if ks:
        _audit("revoked", thread_id, tool, n=len(ks))
    return bool(ks)


# ── r41 网关批准卡预算（Veda 贯穿口径：thread 级计数，升级/重开 run 不重置）──
# hy4 R41-P0×2/P1×3 修正版：
#  - bump 以 (tid, tool_call_id) 幂等去重（resume 重放/batch 二求值不双计）
#  - 预算耗尽→when 不弹卡，ask 调用被 wrap 拒（拒前查 after_model 登记的"爸爸刚批"直通集，
#    批准恢复的执行绝不被吞——P1-3）
#  - 3 张起卡面告警接线到 after_model 的 description（P1-1），不报确切数字
#  - NO-TID 随机桶（r25 教训照抄：宁孤立失效不共享锁死）+ stderr 出声
_CARD_WARN_AT = 3
CARD_BUDGET = 8            # r33 重定位：强提醒线（原"拒绝线"随硬预算退役）——任务累计弹卡达此数，卡面中文强提醒"建议对齐思路"。统计用途，不驱动拒绝。
_task_cards: dict = {}     # {thread_id: [count, ts_first]}
_counted_tc: dict = {}     # {key: 首见 ts} 已计数的 (tid,tc_id 或 fp) 幂等键（r43: set→dict 供 LRU 淘汰）


def bump_blocked(thread_id: str, tool_call_id: str = "", fp: str = "") -> int:
    """拦截发生计一次（幂等：同键只计一次）。返回该线程累计数。
    r43（hy4 审 P1-1/P2-7 收编）：
    - tc_id 空不再裸记——退到参数指纹 fp 当幂等键；两者全空才认裸事件（计数 1 封顶不再复涨）；
    - 幂等键表 2000 上限改按首见时间淘汰旧半（原整 clear 会丢活跃键=长 run 双计提前烧预算）。"""
    key = (thread_id, tool_call_id or fp or "__bare__")
    with _lock:
        if key in _counted_tc:
            return _task_cards.get(thread_id, [0, 0])[0]
        _counted_tc[key] = time.time()
        if len(_counted_tc) > 2000:
            oldest = sorted(_counted_tc.items(), key=lambda kv: kv[1])[:1000]
            for k, _ in oldest:
                _counted_tc.pop(k, None)
        entry = _task_cards.get(thread_id)
        now = time.time()
        if entry is None:
            _task_cards[thread_id] = [1, now]
            _card_pressure_soft[thread_id] = _card_pressure_soft.get(thread_id, 0) + 1  # r2-2 软轨同点（幂等保护后）
        else:
            entry[0] += 1
            _card_pressure_soft[thread_id] = _card_pressure_soft.get(thread_id, 0) + 1
        if len(_task_cards) > 400:  # 按最早首见时间裁（P2：不按插入序误挤老线程）
            oldest = sorted(_task_cards.items(), key=lambda kv: kv[1][1])[:200]
            for k, _ in oldest:
                _task_cards.pop(k, None)
                _card_pressure_soft.pop(k, None)  # r43（hy4 P2-5）：软轨/轮标随硬轨同裁，有界
                _turn_marks.pop(k, None)
        return _task_cards[thread_id][0]


def task_cards(thread_id: str) -> int:
    with _lock:
        e = _task_cards.get(thread_id)
        return e[0] if e else 0


_card_pressure_soft = {}  # {thread_id: 本轮告警计数}（r2-2 软轨）
_turn_marks = {}          # {thread_id: 上次见过的 human 消息数}


def card_pressure(thread_id: str) -> str:
    """卡面告警文案（<3 无；>=3 提醒但不报确切数；>=CARD_BUDGET 中文强提醒——r33 起 English 哨兵退役）。
    r2-2（09-12 基线 W2 案）：告警走软轨——爸爸每发一条新消息（=换题/给新指令）
    告警清零重计，不拿旧任务的账挂新任务的卡；累计账 _task_cards 不受影响。
    r33 重定位：硬预算退役（r32b）后 _task_cards=任务累计弹卡统计（不驱动拒绝），
    驱动两级提醒档位（>=BUDGET-2 强提醒无视软轨换题清零；>=BUDGET 中文强提醒）。
    CB 方案 A"收敛为软轨"经语义分析推翻：强提醒档位引擎是活功能，删=砍功能。"""
    n = task_cards(thread_id)
    # r33（CB 补审 1.2）：英文哨兵 "BUDGET" 退役——硬预算已退役（r32b），n>=8 只是
    # "这个任务弹了很多卡"，按中文告警口径出声；且全仓无 == "BUDGET" 读者，
    # 唯一出口是拼进爸爸卡面（:983→:1002），英文 token 直穿用户可见文案。
    with _lock:
        w = _card_pressure_soft.get(thread_id, 0)
    # r43（hy4 P1-4：软轨清零不得掐断硬轨唯一预警——n=7 且 w=0 静默逼近第 8 张硬拒）：
    # 硬轨逼近预算（>=BUDGET-2）时无视软轨强制出声，只模糊不报数。
    if n >= CARD_BUDGET - 2:
        return ("⚠️ 本任务批准卡已接近配额上限——建议停下来跟爸爸对齐思路，"
                "别一张一张试（爸爸有新指令可发一条消息重开本轮告警，配额本身不重置）。")
    if w >= _CARD_WARN_AT:
        # r42（Eve/NOVA 出生证案）：告警带任务锚+本轮计数——爸爸分得清
        # 是"当前任务的多次"还是"上一任务的遗产"，歧义本身就是狼来了
        return (f"⚠️ 本任务（#{thread_id[:8]}）本轮已弹 {w} 张批准卡仍没走通——"
                "建议停下来跟爸爸对齐思路，别一张一张试。")
    return ""


def note_new_turn(thread_id: str, n_human: int) -> None:
    """[r44 降级为回退通道] 无 task_brief 简报的线程按 human 消息数升序重置软轨；
    有简报的线程改走 soft_reset_task（task_brief 目标 diff 驱动——"继续"不清告警，
    Cora/Lyra 案）。n_human<=0 不记。"""
    if not thread_id or n_human <= 0:
        return
    with _lock:
        last = _turn_marks.get(thread_id, -1)
        if n_human > last:  # r44b-P2-10：删不可达 elif（last 默认 -1，首见即走此分支）
            _turn_marks[thread_id] = n_human
            _card_pressure_soft[thread_id] = 0


_soft_resets: dict = {}  # {tid: 已回血次数}（r44b-P1-6：回血额度衰减 4→3→2→1→0 收敛）


def soft_reset_task(thread_id: str) -> bool:
    """r44b（hy4 Q3 最坏刷卡路径封堵）：新任务软重置——软轨清零；硬预算回血额度
    逐次衰减（4,3,2,1,0）：连续换题刷 4 张一次的路径打不准了；第 N+1 次换题不回血。
    返回是否实际回血（审计用）。"""
    with _lock:
        _card_pressure_soft[thread_id] = 0
        k = _soft_resets.get(thread_id, 0)
        allowance = max(0, CARD_BUDGET // 2 - k)
        _soft_resets[thread_id] = k + 1
        if len(_soft_resets) > 500:
            for kk in list(_soft_resets)[:200]:
                if kk not in _task_cards:
                    _soft_resets.pop(kk, None)
        e = _task_cards.get(thread_id)
        if e and allowance > 0 and e[0] > allowance:
            old = e[0]
            e[0] = allowance
            _audit("soft_reset", thread_id, old=old, new=allowance, nth=k + 1)  # r49 台账批
            print(f"[approvals] soft_reset {thread_id[:8]}: {old}->{allowance} "
                  f"(第{k + 1}次回血, 额度{allowance})", flush=True)
            return True
        return False


def bump_warn(thread_id: str) -> None:
    """[r43 退役] 软轨已并入 bump_blocked 同点递增（幂等保护在其内），本函数
    仅剩单测构造用——生产零调用（hy4 P2-5 死代码指认收编）。"""
    with _lock:
        _card_pressure_soft[thread_id] = _card_pressure_soft.get(thread_id, 0) + 1


def reset_task_cards(thread_id: str) -> int:
    """爸爸显式收尾本任务预算（office /approvals/reset 通道，P1-2 补的口子）。"""
    with _lock:
        _card_pressure_soft.pop(thread_id, None)
        _turn_marks.pop(thread_id, None)
        e = _task_cards.pop(thread_id, None)
        n = e[0] if e else 0
    if n:
        _audit("budget_reset", thread_id, cleared=n)
    return n


def consume(thread_id: str, tool: str, fp: str) -> bool:
    """放行条件：有该次调用的待兑现批准 且 未过期。
    r27 重试竞争窗：批准后 90 秒内同一 fp 最多放行 3 次（覆盖 nudge+用户双唤醒打断
    第一个 run 导致的"批准烧在未完成任务里"）；窗后恢复一次性（消费即焚）。
    米娅换参数重试=不同 fp=再拦，必须逐条请示——原防线不动。"""
    key = (thread_id, tool, fp)
    with _lock:
        ent = _approved.get(key)
        if ent is None:
            _audit("consume_miss", thread_id, tool, fp)
            return False
        ts, used = ent
        now = time.time()
        if now - ts > _TTL_SEC:
            _approved.pop(key, None)
            _audit("consume_expired", thread_id, tool, fp)
            return False
        if now - ts <= _RETRY_WINDOW_SEC:
            if used < _RETRY_MAX:
                _approved[key] = (ts, used + 1)
                _audit("consumed", thread_id, tool, fp, retry=used + 1)
                return True
            _approved.pop(key, None)
            _audit("consume_window_out", thread_id, tool, fp)
            return False
        _approved.pop(key, None)
        _audit("consumed", thread_id, tool, fp)
        return used == 0
