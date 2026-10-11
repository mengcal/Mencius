# -*- coding: utf-8 -*-
"""mia_agent.dept_activity —— 部门"最近成功派活"账本（W1，米娅 R5 愿望①，2026-10-11）。

愿望：米娅判断一个部门是不是"真活着"还得手动派探针——编制清单（manage_departments
list）每部门加一列"最近成功派活"，扫一眼就知道该部门链路最近一次端到端跑通是什么时候。

链路研究结论（派活怎么流的，2026-10-11 实读源码定谳）：
  ① 米娅对部门派活走官方 start_async_task(description, subagent_type=部门名)
    （deepagents AsyncSubAgentMiddleware，graph.py 装配的 AsyncSubAgent 五工具之一）；
  ② 它在 langgraph server 上**新建线程**并以 assistant_id=槽位号发起 run
    （async_subagents.py:266，槽位=departments_config.json 的 slot：dept_N/gm）——
    部门身份的真源=部门线程 metadata.graph_id / 派活时的 subagent_type（部门名）；
  ③ 完成观察唯一出口=check_async_task（async_subagents.py sync L434-435 与 async
    L459-460 两条路径都汇入 _build_check_result→_build_check_command），官方 run.status
    （success/error/cancelled/timeout/running）在这里给出；
  ④ mia_home/tasks.json 的 bk_* 旧账是 webhook 时代的本地待办账，**无部门字段**——
    部门派活从不落那本账（dept_watch v2 扫描式唤醒也不落账），这正是本模块存在的理由。

"成功派活"口径（选定理由随注）：
  派给该槽位的后台任务，官方 run.status 达到 **success** 且结果文本无 result_has_error
  警示（graph.py r40d 真假完工判定字段：产出含失败特征词=假成功，dept_watch/验收侧同
  口径）——即"派出去的活端到端跑通"才算成功；error/cancelled/timeout/running 一律不计。
  主管"请示收尾"的正常结束官方态也是 success，同样计入（能接活能回话=链路活着的证据，
  与"任务做没做完"是两个问题）。
  记录的时间戳 = 该次派活的**派出时刻**（task.created_at = start_async_task 建成 run 的
  时刻，与列名"最近成功派活时间"字面对齐）；confirm_ts（观察确认时刻）同账备查。
  已知盲区（如实注明）：任务成功但米娅从未 check_async_task 的不落账——r25 起的标准
  流程（dept_watch 唤醒→逐个 check）覆盖主链；同一次派活重复 check 幂等不刷账（按派出
  时刻只增不回退，历史任务补查也只补旧时刻、不冲掉更新的记录）。

落盘：settings_mgr.workspace_root()/dept_activity.json（与 tasks.json 同层，跨重启持久）。
边界：只观察不改判——record 内部吞异常，check 主链零影响；不碰 settings_mgr/office 现役逻辑。
"""
import threading
import time

_LEDGER_NAME = "dept_activity.json"
_LOCK = threading.Lock()   # 账本读-改-写互斥（manage_departments _DEPT_LOCK 同款纪律）
_INSTALLED = False


def _ledger_path():
    from settings_mgr import workspace_root  # r37 贯通：数据区单源（容器=mia_home 整目录 rw 挂载）
    return workspace_root() / _LEDGER_NAME


def _load():
    import json as _j
    try:
        d = _j.loads(_ledger_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[dept-activity] 账本读取失败（按空账处理）：{type(e).__name__}: {e}", flush=True)
        return {}
    return d if isinstance(d, dict) else {}


def _parse_ts(s):
    """langgraph 官方 ISO8601（2026-10-11T06:30:00Z）→ epoch；解析失败 None。"""
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _slot_for(agent_name):
    """派活时的部门名（AsyncSubAgent name）→ 槽位号。唯一真源=departments_config.json
    （经 cow_graphs 读档，R69 单源纪律，本模块不自带第二份读档）；总管=graph.py 装配的
    特殊 AsyncSubAgent（graph_id=gm，不在编制表）同样记账备查。查无=None（部门已解散
    编制面也不再显示，跳过即正确）。"""
    if not agent_name:
        return None
    if str(agent_name) == "总管":
        return "gm"
    try:
        from cow_graphs import _load_departments
        for d in _load_departments():
            if d.get("name") == agent_name:
                return d.get("slot")
    except Exception as e:
        print(f"[dept-activity] 部门名→槽位解析失败：{type(e).__name__}: {e}", flush=True)
    return None


def record_check(result, task):
    """check_async_task 观察钩子（_build_check_command 包装器调用）：官方 success 且无
    假成功警示时按槽位落账。任何异常自吞——只观察，绝不挡 check 主链。"""
    try:
        if not isinstance(result, dict) or result.get("status") != "success":
            return
        if result.get("result_has_error"):
            return  # 口径：产出含失败特征=假成功，不计（graph.py r40d 同款判定字段）
        if not isinstance(task, dict):
            return
        slot = _slot_for(task.get("agent_name"))
        if not slot:
            return
        dispatch_ts = _parse_ts(task.get("created_at")) or time.time()
        with _LOCK:
            data = _load()
            ent = data.get(slot) or {}
            try:
                _prev = float(ent.get("dispatch_ts") or 0)
            except (TypeError, ValueError):
                _prev = 0.0
            if _prev >= dispatch_ts:
                return  # 幂等：同一次派活的重复 check / 更旧的历史补查不刷账
            data[slot] = {"dispatch_ts": round(dispatch_ts, 1),
                          "confirm_ts": round(time.time(), 1),
                          "agent_name": task.get("agent_name"),
                          "task_id": task.get("task_id"),
                          "run_id": task.get("run_id")}
            import json as _j
            p = _ledger_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_j.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[dept-activity] {slot} 成功派活落账（dispatch={dispatch_ts:.0f} "
              f"task={str(task.get('task_id'))[:8]}…）", flush=True)
    except Exception as e:
        print(f"[dept-activity] 落账失败（只观察不挡 check 主链）：{type(e).__name__}: {e}", flush=True)


def fmt_last(slot) -> str:
    """manage_departments list 渲染用：槽位最近成功派活的显示串。
    从未 / MM-DD HH:MM（localtime，与 list_external_results 同款格式）/ ?（账本不可读）。"""
    try:
        with _LOCK:
            ent = _load().get(str(slot or ""))
    except Exception:
        return "?"
    if not isinstance(ent, dict) or not ent.get("dispatch_ts"):
        return "从未"
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(float(ent["dispatch_ts"])))
    except Exception:
        return "?"


def _install_hook():
    """包装 deepagents _build_check_command（check 完成观察唯一出口）为"过账不改性"的
    观察器。机制与 graph.py 对 _build_check_result 的补丁同款：模块属性调用期解析，
    包装链自然叠加——本观察在外，graph.py 的真假完工警示（result_has_error）在内。"""
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        from deepagents.middleware import async_subagents as _asam
        _orig = _asam._build_check_command

        def _observing(result, task, tool_call_id):
            record_check(result, task)   # 观察绝不改判：record 内部自吞异常，原样透传
            return _orig(result, task, tool_call_id)

        _asam._build_check_command = _observing
        _INSTALLED = True
        print("[dept-activity] check 观察钩子已挂（部门最近成功派活账）", flush=True)
    except Exception as e:
        print(f"[dept-activity] 钩子安装失败（列将恒显'从未'，不影响其他功能）：{type(e).__name__}: {e}", flush=True)


_install_hook()  # 导入即武装：graph.py 装配期 import tools → 本模块 → 钩子在首次 check 前就位
