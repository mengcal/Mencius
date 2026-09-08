"""R69 确认门 v2：外部批准登记处（评审C A1 方向）。
软门的"重试放行一次"分不清是管理员同意还是模型硬磨；本模块提供【模型之外】的批准通道：
office /approvals（管理员点/敲）→ 该线程该工具的下一次调用直接放行（一次性，消费即焚）。

R73（评审A P3）：批准登记带时间戳，消费时超 24 小时=作废——今天批的动作不会下月还悬着。
R10.2（hy4 ①-1/①-4 审计）：**参数级绑定下沉到本模块**——
  · set_blocked：门拦截时登记"被拦那次的参数指纹"（全局共享，主图/子图同一张表，封跨实例锚点分裂）；
  · approve：管理员批准=对"最近被拦的那次具体调用"开绿灯，指纹随批准固化；
  · consume(tid, tool, fp)：参数指纹一致才放行；**不一致=批准当场作废**（不退回、不续期）——
    封掉"批无害→换恶意参数→多挨一次拦就通行"的无限批准链（空白支票攻击）。
R10.3（评审B 🟡A/⚪E + 评审D 请验2）：
  · approve 带 fp 校验：管理员批准的必须是【他屏幕上看到的那条拦截】——按钮把消息里的指纹带回，
    与登记指纹不符=拒绝（"参数已变，请看最新拦截消息重新决定"），不静默重绑最新一条；
    防时窗调包：助手在管理员读消息与点按钮之间换参数重拦，旧按钮打不中新锚点。
  · approve 无登记指纹=拒批（不再绑 None 覆盖已有批准）——误点/连点不再杀死管理员刚批的有效批准；
  · revoke：未消费批准可撤销（误点后悔药），不再悬 24h。"""
import threading
import time

_lock = threading.Lock()
_approved: dict = {}    # {(thread_id, tool): (bound_fp, approved_ts)} —— bound_fp 永非 None（R10.3 起）
_blocked_fp: dict = {}  # {(thread_id, tool): fp} —— 最近一次被拦调用的参数指纹（管理员批准的对象）
_TTL_SEC = 24 * 3600


def set_blocked(thread_id: str, tool: str, fp: str) -> None:
    """门拦截时登记本次调用指纹（approve 时消费，成为批准的绑定对象）。"""
    with _lock:
        _blocked_fp[(thread_id, tool)] = fp
        if len(_blocked_fp) > 400:  # R10.3（评审C P3）："拦了但从未批"的条目随下沉迁来，裁剪兜底跟着搬
            for k in list(_blocked_fp)[:200]:
                _blocked_fp.pop(k, None)


def approve(thread_id: str, tool: str, fp: str) -> tuple[bool, str]:
    """批准绑定"最近被拦那次的指纹"。
    R10.3：fp 必须与登记指纹一致（管理员批的是他看到的那条）；无登记=无批对象，一律拒。
    R10.4（评审B ⚪C/评审D 🟡 生产收紧）：fp 必填——空 fp 兼容分支是时窗调包的理论残口，
    前端已随包发版，旧缓存页面存活期结束=残口消失；手动 curl 批准请从拦截消息复制〔fp:…〕。
    返回 (ok, 理由)。"""
    with _lock:
        if not fp:
            return False, "缺少指纹 fp——请从拦截消息里的〔fp:…〕原样复制（批准与参数绑定）"
        cur = _blocked_fp.get((thread_id, tool))
        if cur is None:
            return False, "没有待批准的拦截记录（可能已被消费/过期，或工具名不匹配）"
        if fp != cur:
            return False, "参数已变——请看最新一条拦截消息上的指纹，重新决定再批"
        _blocked_fp.pop((thread_id, tool), None)
        _approved[(thread_id, tool)] = (cur, time.time())
        if len(_approved) > 500:  # 慢泄漏兜底：超量清掉最老一半
            cutoff = sorted(ts for _, ts in _approved.values())[-250]
            for k in [k for k, (_, ts) in _approved.items() if ts < cutoff]:
                _approved.pop(k, None)
    return True, "ok"


def revoke(thread_id: str, tool: str) -> bool:
    """R10.3（评审B ⚪E）：撤销未消费的批准/拦截登记（误点后悔药，不再悬 24h）。"""
    with _lock:
        hit = _approved.pop((thread_id, tool), None) is not None
        hit = _blocked_fp.pop((thread_id, tool), None) is not None or hit
    return hit


def consume(thread_id: str, tool: str, fp: str) -> bool:
    """放行条件：有待兑现批准 且 未过期 且 参数指纹与批准时绑定的一致。
    任何不一致=批准已弹出作废——助手换参数重试只会再被拦，必须重新向管理员请示。"""
    with _lock:
        got = _approved.pop((thread_id, tool), None)
    if got is None:
        return False
    bound_fp, ts = got
    if time.time() - ts > _TTL_SEC:
        return False
    return bound_fp is not None and bound_fp == fp
