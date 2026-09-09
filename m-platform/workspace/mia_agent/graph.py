# -*- coding: utf-8 -*-
"""mia_agent/graph.py —— 装配：SDK 补丁 + 家目录 + 子代理 + skills_lock + create_deep_agent
拆分来源：D:\\m\\workspace\\agent_multimodel.py：
  · 原 L808-816（BASE/MEMORY_FILE 家目录建档）——BASE 按方案改为 parent.parent（包目录上一级
    = 原 monolith 所在的工作区根；部署时 mia_agent/ 须位于工作区根下，BASE 才指对）。
  · 原 L130-162（cow_task SDK monkey-patch + confirmLevel 残留探测）——按方案置本模块顶部
    （全局副作用，只执行一次）。
  · 原 L911-955（_compaction_middleware）——方案未单列，属装配件，归本模块。
  · 原 L957-1034（拆分方案 #7：_load_departments + _build_async_subagents + skills_lock +
    create_deep_agent 装配）。
依赖：包内 prompts/sandbox/confirm_gate/store/models/tools 全部模块；
包外 deepagents / search_tools / scribe_hook / run_config / skills_lock / providers（懒）/
cow_graphs（懒）。
被引用：D:\\m\\workspace\\agent_multimodel.py（部署后仅剩 `from mia_agent.graph import agent`
一行转发）；mia_agent/tools.py 的工具函数运行时按需取本模块 BASE。
"""
from pathlib import Path  # 原 L11

from deepagents import AsyncSubAgent, create_deep_agent  # 原 L961 + L67（L67 的 SubAgent 未用已删）

# ── 家目录：记忆/技能/工作文件都住这，跨对话持久 ──（原 L808-816；BASE 由原 parent 改 parent.parent）
BASE = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE / "mia_home" / "memory" / "MEMORY.md"
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
if not MEMORY_FILE.exists():
    MEMORY_FILE.write_text(
        "# 工作平台·后台任务队列记忆\n\n## 最近任务\n\n## 踩坑记录\n",
        encoding="utf-8",
    )

# ── R68 侧栏防污染补丁（官方姿势调研结论落地）───────────────────────────（原 L130-155）
# deepagents 0.7.11 的 start_async_task 建后台线程是裸调 threads.create()（metadata 为空，
# async_subagents.py:263/303 源码实锤），官方 demo UI 对此无解——后台部门线程全漏进侧栏。
# SDK 本身支持 metadata 参数（langgraph_sdk 0.4.4 实核），故在 Python 进程给 SDK 的 create
# 统一打 cow_task=True 标签；前端 useThreads 既有的 cow_task 排除逻辑(useThreads.ts:89)即刻生效。
# 注意：只影响容器内 Python 侧建线程（=后台工人岗线程），浏览器 JS 建的主对话线程不经此路。
try:
    from langgraph_sdk._async.threads import ThreadsClient as _ATC
    from langgraph_sdk._sync.threads import SyncThreadsClient as _STC

    def _cow_md(metadata):
        md = dict(metadata or {})
        md["cow_task"] = True
        return md

    _orig_acreate = _ATC.create
    async def _acreate(self, *a, metadata=None, **kw):
        return await _orig_acreate(self, *a, metadata=_cow_md(metadata), **kw)
    _ATC.create = _acreate

    _orig_screate = _STC.create
    def _screate(self, *a, metadata=None, **kw):
        return _orig_screate(self, *a, metadata=_cow_md(metadata), **kw)
    _STC.create = _screate
except Exception as _e:  # SDK 结构升级对不上时不炸平台（侧栏顶多回到旧样子）
    print(f"[agent] cow_task 标记补丁未生效（不影响启动）：{_e}", flush=True)

try:  # R68（评审C D1）：R66 分档挪家后旧节残留要出声，防"strict 被静默降成 auto_edit"这类暗坑（原 L157-162）
    from settings_mgr import load_settings as _ls_probe
    if "confirmLevel" in (_ls_probe().get("subagents") or {}):
        print("[agent] ⚠ 检测到旧节 subagents.confirmLevel 残留（现行为 general.confirmLevel）——旧值已忽略，请清理设置档防误导", flush=True)
except Exception:
    pass

# ── 包内模块（拆分后各归其位）──
from mia_agent.prompts import _system_prompt  # 原 L13-66
from mia_agent.sandbox import SandboxedShellBackend  # 原 L67-117
from mia_agent.confirm_gate import ConfirmGateMiddleware  # 原 L212-464
from mia_agent.store import MiaState, _STORE  # 原 L120-122/L165-168/L804-854
from mia_agent.models import _interrupt_on, boss_model  # 原 L124/L858-908
from mia_agent.tools import (_load_mcp_tools, dispatch_background_task, edit_memory, email,  # 原 L171-210/L466-802
                             manage_departments, search_knowledge_base)

# ── 包外：搜索/中间件（原 L125-127）──
from search_tools import web_search, web_search_bocha, web_search_tavily, web_search_metaso  # 原 L125
from scribe_hook import ScribeMiddleware  # 原 L126
from run_config import RunConfigMiddleware  # 原 L127

import skills_lock as _skills_lock  # 原 L999


# ── R59 官方多层架构：工人岗编入部门（departments_config.json），部门组长图注册为
#    独立 graph（cow_graphs.py），助手通过官方 AsyncSubAgent 五工具异步派活：
#    start/check/update/cancel/list——派活即回不阻塞，可中途转向/取消，任务状态
#    存专用 async_tasks 通道（防上下文压缩丢失）。──（原 L957-960）


def _load_departments():  # 原 L964-971
    # R69（评审C E1 双链）：唯一实现收进 cow_graphs，本模块函数级委托——两份读档=改一漏一的种子，拔掉。
    try:
        from cow_graphs import _load_departments as _cow_load
        return _cow_load()
    except Exception as e:
        print(f"[departments] 配置读取失败：{e}", flush=True)
        return []


def _build_async_subagents():  # 原 L974-991
    out = []
    for d in _load_departments():
        if not (d.get("slot") and d.get("name") and d.get("supervisor")):
            continue
        workers = "、".join(w.get("name", "") for w in d.get("workers", []))
        out.append(AsyncSubAgent(
            name=d["name"],
            description=f"{d['name']}组长（工人岗：{workers}）。接到部门任务后拆解派给工人岗、验收汇总上交。",
            graph_id=d["slot"],
        ))
    # R64 调度层（管理员的军事层级）：跨部门协同任务助手转告调度，调度分解协调各部门
    out.append(AsyncSubAgent(
        name="调度",
        description="调度（任务分解官）。跨部门协同任务转告给他：他分解成各部门的活、协调各部门组长并行执行、汇总结果上交。单一部门的任务不用他。",
        graph_id="gm",
    ))
    # 封 deepagents 自动注入的 general-purpose 影子子代理：它继承主图全工具却不带
    # ConfirmGate（deepagents/graph.py 注入条件=无同名 spec；其栈过滤自定义中间件），
    # 一次 task 批准=放出无门全权代理。照部门图已验证的死胡同样板占领槽位。
    from deepagents.middleware.subagents import CompiledSubAgent
    from langgraph.graph import StateGraph, MessagesState, END

    def _gp_refuse(state):
        return {"messages": [{"role": "assistant", "content":
            "general-purpose 槽位已按编制纪律退役：主图只准派在编部门/调度（异步子代理）或用在编工具面干活，"
            "派到这里只会得到退回指令。"}]}
    _gpe = StateGraph(MessagesState)
    _gpe.add_node("gp_refuse", _gp_refuse)
    _gpe.set_entry_point("gp_refuse")
    _gpe.add_edge("gp_refuse", END)
    out.append(CompiledSubAgent(
        name="general-purpose",
        description="已退役槽位——不要派活（编制纪律：只准用在编部门/调度/工具面，派过来只会得到退回指令）。",
        runnable=_gpe.compile(),
    ))
    return out


_async_subagents = _build_async_subagents()  # 原 L994

# ── R10.3 skills_lock（评审A/评审B 方案落地）：技能清单哈希锁——挂载回归保险 ──（原 L996-1009）
# 基线落 secrets 卷；不符=本组技能整体停用（宁可不带技能不裸奔）+日志+审计。
# 改挂载=必重启=必再校验，故启动校验覆盖回归场景；运行中宿主改文件到重启前不被捕获（诚实清单）。
_SKILLS_DIR = BASE / "mia_home" / "skills"  # 原 L1000: Path(__file__).resolve().parent / "mia_home" / "skills"
if _skills_lock.enabled():
    _SKILLS_BAD = _skills_lock.verify(_SKILLS_DIR, _skills_lock.ensure_baseline(_SKILLS_DIR))
    if any(_SKILLS_BAD.values()):
        print(f"[skills_lock] 技能清单不符，本组技能已停用：{_SKILLS_BAD}（管理员在设置页重新登记后重启）", flush=True)
        _SKILLS = []
    else:
        _SKILLS = ["skills/"]
else:
    _SKILLS = ["skills/"]


# ===== 官方对话压缩（deepagents SummarizationMiddleware，管理员定调：功能用官方件）=====（原 L911-955）
# 参数来自设置页 Experience→界面（interface.compaction 节）：
#   enabled / threshold(Token Threshold) / cap(Token Cap) / retained(Retained Messages) / prompt(压缩提示词)
# 没配置 = 官方默认行为；关掉 = 不挂压缩中间件。
def _compaction_middleware():
    try:
        from settings_mgr import load_settings
        c = (load_settings().get("interface", {}) or {}).get("compaction", {}) or {}
    except Exception:
        c = {}
    if not c.get("enabled", True):
        return []
    kwargs = {}
    try:
        threshold = int(c.get("threshold") or 0)
        cap = int(c.get("cap") or 0)
        if threshold > 0:
            if cap > 0:
                threshold = min(threshold, cap)
            kwargs["trigger"] = {"tokens": threshold}
        if str(c.get("retained") or "") != "" and int(c["retained"]) > 0:
            kwargs["keep"] = ("messages", int(c["retained"]))
        if str(c.get("prompt") or "").strip():
            kwargs["summary_prompt"] = str(c["prompt"]).strip()
    except Exception:
        pass  # 参数脏了就走官方默认
    # R69（评审B⚪/MK 教训）：压缩模型可配 interface.compaction.provider/model——
    # 默认不配=用 boss；配了便宜档（如 书生x号/intern-latest）压缩就不烧大模型。配置无效出声回退。
    comp_model = boss_model
    try:
        if str(c.get("model") or "").strip():
            from providers import make_model
            comp_model = make_model(str(c.get("provider") or ""), str(c["model"]).strip(), thinking="off")
            print(f"[compaction] 压缩模型={c.get('provider')}/{c['model']}", flush=True)
    except Exception as e:
        print(f"[compaction] ⚠ 压缩模型配置无效（{e}），回退 boss", flush=True)
    try:
        from deepagents.middleware.summarization import SummarizationMiddleware
        return [SummarizationMiddleware(
            model=comp_model,
            backend=SandboxedShellBackend(root_dir=str(BASE / "mia_home")),
            **kwargs,
        )]
    except Exception:
        return []  # 官方中间件不可用就不挂，绝不挡启动


# MCP 工具真名注入门的来源集合（库命名不带 mcp__ 前缀，startswith 判定永不命中——
# 门按来源强制外部批准+路径自锁）。
_mcp_tools = _load_mcp_tools()
ConfirmGateMiddleware._MCP_NAMES = {str(t.name).strip().lower() for t in _mcp_tools}

agent = create_deep_agent(  # 原 L1011-1034
    model=boss_model,
    name="mia",
    # ── 官方 human-in-the-loop：动手跑代码前必须经管理员确认（deepagents 官方 interrupt_on）──
    # 设置页 subagents.interruptOnExecute=false 可关（默认开，省 token 防瞎跑）
    interrupt_on=_interrupt_on(),
    system_prompt=_system_prompt(),  # 设置页 general.system_prompt 优先，_DEFAULT_PROMPT 只是出厂默认
    memory=["memory/MEMORY.md"],
    store=_STORE,  # R63 官方 store（PG 永久记忆）：跨线程共享，checkpointer 之外的全局记忆层
    skills=_SKILLS,  # R10.3 skills_lock：验证过的技能清单（不符=空列表整体停用）
    # R59：AsyncSubAgent 对象直接放进官方 subagents 参数（0.5.0 起同步/异步合并为单一参数，
    # deepagents 内部自动分流：同步→SubAgentMiddleware，异步→AsyncSubAgentMiddleware 五工具）
    subagents=_async_subagents,
    tools=[dispatch_background_task, search_knowledge_base, edit_memory, manage_departments, email,  # R72 +邮箱托管
           *_mcp_tools, web_search, web_search_metaso, web_search_bocha, web_search_tavily],
    backend=SandboxedShellBackend(root_dir=str(BASE / "mia_home")),
    state_schema=MiaState,
    middleware=[
        ConfirmGateMiddleware(),  # R47 动态确认门（四档，改设置即时生效）
        ScribeMiddleware(root_dir=BASE / "mia_home"),
        *_compaction_middleware(),
        RunConfigMiddleware(),  # 输入框的模型选择/联网开关在这里生效
    ],
)
