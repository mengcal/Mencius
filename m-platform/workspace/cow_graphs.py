# -*- coding: utf-8 -*-
"""cow_graphs.py — 工人岗部门图工厂（R59 官方多层架构，2026-08-31 作者）

按 departments_config.json 构建各部门组长图（每图内含本部门工人岗为同步 SubAgent），
导出 dept_0/dept_1/dept_2 三个编译图，由 langgraph.json 注册——
助手（agent 图）通过官方 AsyncSubAgent 异步派活给部门图，不阻塞对话。

设计要点：
- 人事权在助手：manage_departments 工具增删工人岗/任命组长，改完即时生效（工厂+缓存，零重启）
- 固定 4 个槽位（dept_0..dept_3），未配置的槽位生成占位图（保证注册不失败）
- 部门组长图自带 RunConfigMiddleware（用量记录进观测台）
"""
import json
from pathlib import Path

from deepagents import create_deep_agent, SubAgent
# R79①（评审C P1）：execute 全平台进沙箱——R76 只换了主图/异步子代理，部门图与调度图漏网。
# 部门/调度图的 backend 在函数内引 agent_multimodel.SandboxedShellBackend（同进程导入，避顶层环）。

BASE = Path(__file__).resolve().parent
_DEPT_CONFIG = BASE / "departments_config.json"
_MAX_SLOTS = 4


def _load_departments():
    try:
        cfg = json.loads(_DEPT_CONFIG.read_text(encoding="utf-8"))
        return cfg.get("departments") or []
    except Exception as e:
        print(f"[cow_graphs] departments_config 读取失败：{e}", flush=True)
        return []


def _role_model(role: str, **kw):
    """R64 去硬编码：部门模型一律按「角色名」从统一配置（设置页 agents 节优先）解析。
    departments_config.json 只写角色（coder/visual/...），不写 provider 名——
    管理员在设置页改服务商名（今天叫智谱0175明天叫智谱二号），部门自动跟着变，绝不再失配。"""
    from settings_mgr import load_agents_config
    from providers import make_model

    cfg = load_agents_config()
    c = cfg.get(role) or {}  # R65：越权兜底已删——不借 archivist，没配好就占位（调用才报错，绝不偷干活）
    # R77（管理员定调：思考强度是岗位性质，不是模型属性——同一岗位换模型，思考要求不变）：
    # 岗位=role，settings.agents[role].thinking 是该岗唯一的思考真源；调用方显式 kw 可覆盖（无则岗位说了算）。
    if "thinking" not in kw:
        _t = c.get("thinking")
        if _t not in (None, "", "default"):
            kw = {**kw, "thinking": _t}
    try:
        return make_model(c.get("provider", ""), c.get("model", ""), **kw)
    except Exception as e:
        print(f"[cow_graphs] 警告：角色 {role} 未配置/不可用（{e}）——占位模型顶替，请到设置页配置后重启", flush=True)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="unconfigured", api_key="EMPTY", base_url="https://unconfigured.invalid")


def _build_dept_graph(dept: dict, slot: str):
    """构建一个部门组长图：组长模型 + 本部门工人岗（同步 SubAgent，部门内阻塞协作）。"""
    from agent_multimodel import SandboxedShellBackend  # R79①：execute 进沙箱（与主图同款）

    sup = dept.get("supervisor") or {}
    workers = dept.get("workers") or []
    dept_name = dept.get("name") or slot

    sup_kwargs = {}  # R77：thinking 不再是"跟着模型/部门文件走"——真源=settings.agents[role].thinking（_role_model 内部按岗位取）

    subagents = []
    from agent_multimodel import ConfirmGateMiddleware, search_knowledge_base  # 同进程（langgraph server 全图单进程），函数内引避免顶层环
    from search_tools import web_search
    for w in workers:
        wkwargs = {}  # R77：同上——岗位思考要求由 _role_model 从 settings.agents[role] 取，这里不再从部门文件注入
        # R66 #5 工具收口：显式发工具，绝不靠"缺省继承父图"（官方 graph.py:727 spec 无 tools 就整份继承）
        # R68 接线（评审A E4/评审B⚪/评审D E1/评审E三.2.2 四家同报）：departments_config 的 worker.tools
        # 从此真正生效——按名字从发放池领；未配置默认=知识库（researcher 加联网）。池外名字出声不静默。
        _tool_pool = {"search_knowledge_base": search_knowledge_base, "web_search": web_search}
        # execute/ls/read_file/write_file/edit_file/glob/grep 由官方 FilesystemMiddleware 自动注入，
        # 不在"自定义工具池"管辖——配置里出现属正常，不告警（R68 修作者自造噪音）
        _fs_auto = {"execute", "ls", "read_file", "write_file", "edit_file", "glob", "grep", "delete", "task"}
        names = [t for t in (w.get("tools") or []) if isinstance(t, str)]
        if not names:
            names = ["search_knowledge_base"] + (["web_search"] if (w.get("role") or w["name"]) == "researcher" else [])
        wtools = []
        for tn in names:
            if tn in _fs_auto:
                continue  # 官方自动栈已提供，无需也无法经 tools 参数再发
            _t = _tool_pool.get(tn)
            if _t is None:
                print(f"[cow_graphs] ⚠ 工人岗 {w['name']} 配置的工具「{tn}」不在发放池（自定义工具现有 {list(_tool_pool)}），已忽略", flush=True)
            else:
                wtools.append(_t)
        subagents.append(SubAgent(
            name=w["name"],
            description=(w.get("desc") or f"{dept_name}·{w['name']}"),
            system_prompt=w.get("system_prompt", f"你是{dept_name}的{w['name']}。"),
            model=_role_model(w.get("role") or w["name"], **wkwargs),
            tools=wtools,
            # R66 层级确认门·官方规则(0.7.11 subagents.py)：声明式工人岗不继承父图自定义 middleware，门必须各挂各的
            middleware=[ConfirmGateMiddleware(sub_mode=True)],
        ))

    # R66 #5 封影子编制：deepagents 会自动给图塞一头 general-purpose（组长可绕开编制用它）。
    # 官方 override 通道=自带同名 spec 即不再自动加。给一头"退役死胡同"，task 派它只会领回一句军规。
    from deepagents.middleware.subagents import CompiledSubAgent
    from langgraph.graph import StateGraph, MessagesState, END

    def _gp_refuse(state):
        return {"messages": [{"role": "assistant", "content":
            "general-purpose 槽位已按军事纪律退役：组长只准派部门在编工人岗（见部门编制），把活交给在编工人岗重做。"}]}
    _gpe = StateGraph(MessagesState)
    _gpe.add_node("gp_refuse", _gp_refuse)
    _gpe.set_entry_point("gp_refuse")
    _gpe.add_edge("gp_refuse", END)
    subagents.append(CompiledSubAgent(
        name="general-purpose",
        description="已退役槽位——不要派活（军事纪律：只准用在编工人岗，派过来只会得到退回指令）。",
        runnable=_gpe.compile(),
    ))

    supervisor_model = _role_model(sup.get("role") or "boss", **sup_kwargs)

    from run_config import RunConfigMiddleware  # 部门用量也进观测台
    graph = create_deep_agent(
        model=supervisor_model,
        name=slot,
        system_prompt=sup.get("system_prompt", f"你是{dept_name}组长。拆解任务、派给工人岗、汇总上交。"
                         "军事纪律：工人岗上报请示时，你无权批准、也不得亲自代跑其活（不越级不代劳），"
                         "把请示原样上报你的上级，授权自上而下。"
                         "只准派部门在编工人岗，general-purpose 是退役槽位，派过去=失职。"),
        tools=[search_knowledge_base],  # R66 #5：组长判断派活前可查私人知识库（此前无工具，派活铁律落空）
        subagents=subagents,
        backend=SandboxedShellBackend(root_dir=str(BASE / "mia_home")),
        # R66：组长图挂子层门（拦截=上报请示，不弹管理员）；interrupt_on 官方继承表管不到自定义 middleware
        middleware=[RunConfigMiddleware(), ConfirmGateMiddleware(sub_mode=True)],
    )
    return graph


def _placeholder(slot: str):
    """未配置槽位的占位图：被派活时返回提示（不报错不挡启动）。"""
    from langgraph.graph import StateGraph, MessagesState, END

    def echo(state):
        return {"messages": [{"role": "assistant", "content": f"部门 {slot} 未配置（departments_config.json），请管理员或助手先在设置中配置。"}]}

    g = StateGraph(MessagesState)
    g.add_node("echo", echo)
    g.set_entry_point("echo")
    g.add_edge("echo", END)
    return g.compile()


# ===== R64 工厂+缓存（MK agent_factory 同款，管理员要的人事权核心）=====
# 部门图不再启动时烘焙死——departments_config.json 一变，下次派活自动重建，零重启。
# 助手的 manage_departments 工具改配置 → invalidate_dept_cache() → 人事变动立即生效。
_dept_cache: dict = {}   # slot -> compiled graph
_cfg_mtime: float = 0.0


def invalidate_dept_cache():
    """助手人事变动后调用：清部门图缓存，下次派活按新配置重建。"""
    global _cfg_mtime
    _dept_cache.clear()   # 关键：整表清空。只置 mtime=0 会导致仅首个被访问的 slot 重建、其余仍吃旧图（评审A#2/评审B#4）
    _cfg_mtime = 0.0


def _get_dept_graph(slot: str):
    """工厂：配置 mtime 变了才重建，否则用缓存（MK clear_agent_cache 同款思路）。"""
    global _cfg_mtime
    import os
    mtime = _DEPT_CONFIG.stat().st_mtime if _DEPT_CONFIG.exists() else 0
    if slot in _dept_cache and mtime == _cfg_mtime:
        return _dept_cache[slot]
    depts = {d.get("slot"): d for d in _load_departments() if d.get("slot")}
    dept = depts.get(slot)
    if dept and dept.get("supervisor") and dept.get("workers"):
        try:
            g = _build_dept_graph(dept, slot)
            names = [w["name"] for w in dept["workers"]]
            print(f"[cow_graphs] {slot} 重建 = {dept.get('name')}（工人岗：{'、'.join(names)}）", flush=True)
        except Exception as e:
            print(f"[cow_graphs] {slot} 构建失败，用占位图：{e}", flush=True)
            g = _placeholder(slot)
    else:
        print(f"[cow_graphs] {slot} 未配置，用占位图", flush=True)
        g = _placeholder(slot)
    _dept_cache[slot] = g
    _cfg_mtime = mtime
    return g


def _inner_config(config):
    """R80（bk_003 端到端抓出·dept 后台 run NotImplementedError）：langgraph-api 把它的持久化
    saver 注入外层运行 config 的 configurable.__pregel_checkpointer（实测键名，非 "checkpointer"）——
    入口图把 config 透传给内层工厂图做【进程内同步 invoke】时，内层同步 pregel 调 saver.get_tuple，
    而平台 saver 只实现异步接口（aget_tuple），同步版抛 NotImplementedError。内层图本就不落盘
    （checkpointer=None，服务器负责持久化入口图状态），剥掉注入键与 checkpoint_id，保留 thread_id
    等 configurable（子图 get_config()/_tid() 依赖）。"""
    try:
        c = dict(config or {})
        conf = dict(c.get("configurable") or {})
        conf.pop("__pregel_checkpointer", None)
        conf.pop("checkpoint_id", None)
        c["configurable"] = conf
        return c
    except Exception:
        return config


def _make_entry_graph(slot: str):
    """轻量入口图（官方 StateGraph 编译，供 langgraph.json 注册）：
    内部 invoke 工厂构建的部门图——配置变更自动生效，人事权在助手手里。"""
    from langgraph.graph import StateGraph, MessagesState, END

    def run(state, config):  # R68 修 评审C C1：入口图必须把 config 传进工厂图，否则子图 get_config() 拿不到
        g = _get_dept_graph(slot)
        return g.invoke(state, config=_inner_config(config))

    e = StateGraph(MessagesState)
    e.add_node("dept", run)
    e.set_entry_point("dept")
    e.add_edge("dept", END)
    return e.compile()


dept_0 = _make_entry_graph("dept_0")
dept_1 = _make_entry_graph("dept_1")
dept_2 = _make_entry_graph("dept_2")
dept_3 = _make_entry_graph("dept_3")


# ===== R64 调度层（管理员的军事层级：助手→调度→部门组长→工人岗）=====
# 调度=任务分解官：跨部门协同任务由助手转告调度，调度拆成各部门的活分派给
# 部门组长（CompiledSubAgent 包装部门入口图），收齐结果汇总上交。单一部门任务不经调度。
def _get_gm_graph():
    global _cfg_mtime
    import os
    mtime = _DEPT_CONFIG.stat().st_mtime if _DEPT_CONFIG.exists() else 0
    if "_gm" in _dept_cache and mtime == _cfg_mtime:
        return _dept_cache["_gm"]
    from deepagents.middleware.subagents import CompiledSubAgent

    gm_cfg = {}
    try:
        gm_cfg = (json.loads(_DEPT_CONFIG.read_text(encoding="utf-8")) or {}).get("general_manager") or {}
    except Exception:
        pass
    subs = []
    for d in _load_departments():
        slot = d.get("slot")
        if slot and d.get("supervisor") and d.get("workers"):
            names = "、".join(w.get("name", "") for w in d["workers"])
            subs.append(CompiledSubAgent(
                name=d.get("name", slot),
                description=f"{d.get('name')}组长（工人岗：{names}）。把本部门那部分任务接走办，办完交结构化结果。",
                runnable=_get_dept_graph(slot),
            ))
    model = _role_model(gm_cfg.get("role") or "boss")
    # R66 #5：调度辖下同样封 general-purpose 影子（调度绕过部门组长找"临时工"=绕编制）
    from langgraph.graph import StateGraph as _SG, MessagesState as _MS, END as _END

    def _gm_gp_refuse(state):
        return {"messages": [{"role": "assistant", "content":
            "general-purpose 槽位已退役：调度只准把活分派给在编部门组长，重新分派。"}]}
    _gpe = _SG(_MS)
    _gpe.add_node("gp_refuse", _gm_gp_refuse)
    _gpe.set_entry_point("gp_refuse")
    _gpe.add_edge("gp_refuse", _END)
    subs.append(CompiledSubAgent(
        name="general-purpose",
        description="已退役槽位——调度只准派在编部门组长。",
        runnable=_gpe.compile(),
    ))
    # R66 接线时揪出 R64 潜伏 NameError：本函数此前没有 import RunConfigMiddleware，gm 真被派活即崩（注册≠可用，验证盲区）
    from run_config import RunConfigMiddleware
    from agent_multimodel import ConfirmGateMiddleware, SandboxedShellBackend  # R79①：调度图 execute 也进沙箱
    g = create_deep_agent(
        model=model,
        name="general_manager",
        system_prompt=gm_cfg.get("system_prompt",
            "你是调度（任务分解官）。把跨部门任务分解成各部门的活，分派给部门组长，收齐结果汇总上交。"
            "分派只准用在编部门组长，general-purpose 是退役槽位。"),
        subagents=subs,
        backend=SandboxedShellBackend(root_dir=str(BASE / "mia_home")),
        # R66 层级确认门：调度图子层模式（拦截=上报助手请示，不弹管理员）；组长/工人岗已在 _build_dept_graph 挂好
        middleware=[RunConfigMiddleware(), ConfirmGateMiddleware(sub_mode=True)],
    )
    _dept_cache["_gm"] = g
    _cfg_mtime = mtime
    print(f"[cow_graphs] 调度就绪（下辖 {sum(1 for s in subs if s['name'] != 'general-purpose')} 个部门组长）", flush=True)
    return g


def _make_gm_entry():
    from langgraph.graph import StateGraph, MessagesState, END

    def run(state, config):  # R68 修 评审C C1（调度同款）：config 透传，放行标记不再全员挤 thread_id="" 共享桶
        g = _get_gm_graph()
        return g.invoke(state, config=_inner_config(config))  # R80：剥服务器注入的 checkpointer（见 _inner_config）

    e = StateGraph(MessagesState)
    e.add_node("gm", run)
    e.set_entry_point("gm")
    e.add_edge("gm", END)
    return e.compile()


gm = _make_gm_entry()
