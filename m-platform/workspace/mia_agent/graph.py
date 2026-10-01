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
# r36（09-27 爸令工作区分区）：容器域根可配（settings.workspace.containerRoot，默认 mia_home=零行为变更）。
# 装配期读一次——改它=低频配置动作，重启容器生效（与档位文件同纪律）。
def _container_root() -> str:
    # r37：收敛到 settings_mgr.workspace_root 单源（本函数保留兼容旧引用）
    from settings_mgr import workspace_root as _wr
    return _wr().name
_WS_ROOT = _container_root()
MEMORY_FILE = __import__("settings_mgr").workspace_root() / "memory" / "MEMORY.md"  # r37 贯通
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
if not MEMORY_FILE.exists():
    MEMORY_FILE.write_text(
        "# 工作平台·小全车间记忆\n\n## 最近任务\n\n## 踩坑记录\n",
        encoding="utf-8",
    )

# ── R68 侧栏防污染补丁（官方姿势调研结论落地）───────────────────────────（原 L130-155）
# deepagents 0.7.11 的 start_async_task 建后台线程是裸调 threads.create()（metadata 为空，
# async_subagents.py:263/303 源码实锤），官方 demo UI 对此无解——后台部门线程全漏进侧栏。
# SDK 本身支持 metadata 参数（langgraph_sdk 0.4.4 实核），故在 Python 进程给 SDK 的 create
# 统一打 cow_task=True 标签；前端 useThreads 既有的 cow_task 排除逻辑(useThreads.ts:89)即刻生效。
# 注意：只影响容器内 Python 侧建线程（=后台牛马线程），浏览器 JS 建的主对话线程不经此路。
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

# r39e（09-29 递归爆案第二刀）：deepagents check_async_task 的 error fallback 是笼统文案
# （"The async subagent encountered an error."），而 langgraph server 不持久化 run.error
# （PG run 表无此列、checkpoint 亦无 error 通道，真实异常只在 worker 日志）——米娅看不到
# 真实死因→连查打转→主图 100 层递归爆（当日实案）。patch：error 空时给诊断指引，防干等循环。
# r39t（09-30 米娅验收单⑤升级）：error 附诊断包（线程消息步数+最后发言片段），
# running 附静默信号（run 更新超 5 分钟="疑似静默"——米娅点名要的信号，直接干掉"脑补已完成"）。
try:
    from deepagents.middleware import async_subagents as _asam
    _orig_bcr = _asam._build_check_result

    def _diag_from_values(thread_values):
        """从线程状态挖诊断包：消息步数+最后一条消息片段（卫生版：脱敏+截断——Eve 洞3）。"""
        try:
            import re as _re
            msgs = (thread_values or {}).get("messages") or []
            if not msgs:
                return None
            last = msgs[-1]
            content = last.get("content", "") if isinstance(last, dict) else str(last)
            if isinstance(content, list):
                content = " ".join(x.get("text", "") for x in content if isinstance(x, dict))
            content = _re.sub(r"(sk-|AKIA|Bearer\s+)[A-Za-z0-9_\-]+", r"\1[REDACTED]", content)
            kind = (last.get("type") or last.get("role") or "?") if isinstance(last, dict) else "?"
            return {"steps": len(msgs), "last_kind": str(kind), "last_snippet": str(content)[:120]}
        except Exception:
            return None

    _LAST_STEPS: dict = {}  # r39t v2（Eve 洞1）：{task_id: 上次消息步数}——静默=超时+步数零增量

    def _bcr_with_guidance(run, thread_id, thread_values):
        result = _orig_bcr(run, thread_id, thread_values)
        diag = _diag_from_values(thread_values)
        steps = diag["steps"] if diag else 0
        if result.get("status") == "error" and str(result.get("error", "")).startswith("The async subagent"):
            detail = ""
            if diag:
                # Eve 洞2：静默/诊断信号自证（步数+片段+口径随包，查账人引用现成证据）
                detail = (f"诊断包：该任务线程已累积 {diag['steps']} 条消息，最后一条是 {diag['last_kind']} 说："
                          f"「{diag['last_snippet']}」（Eve 洞2：活性证据=消息步数，勿凭印象脑补）——"
                          "牛马最后停在什么状态一目了然。")
            # Eve 洞4：r39e 防打转文案保留追加（09-29 递归爆实案淬出来的，不整个换掉）
            result["error"] = ("后台任务失败（langgraph 未持久化错误详情，真实异常只在 worker 日志）。"
                               + (" " + detail if detail else "")
                               + " 不要连续重查——把 task_id 交给管理员（爸爸/celia（西莉亚））挖日志定因，"
                               "或改派前台会话验证。连查打转会撞递归上限（09-29 实案）。")
        elif result.get("status") == "success":
            # r40d（米娅运营反馈⑥）：任务"执行完成"≠"产出成功"——result 文本含失败特征时
            # 打透明警示字段（status 保持官方值不动，官方下游语义零破坏；dept_watch/米娅
            # 验收侧读 result_has_error 判真假完工）。宁误报不漏报=警示字段不是判定。
            try:
                import re as _re
                _rtext = str(result.get("result") or result.get("output") or "")
                if _rtext and _re.search(r"失败|错误|未配置|异常|无法|不支持|encountered an error", _rtext):
                    result["result_has_error"] = True
                    result["result_note"] = "产出文本含失败特征（警示字段，status 语义未动）——下游判定请读本字段"
            except Exception:
                pass
        elif result.get("status") == "cancelled":
            # r40d（米娅 M1.1 开工撞雷：cancelled 双语义）——cancelled 是 **run 层**状态
            # （新消息打断整个 run），不代表任务未创建：start_async_task 的 Command update
            # 在打断前已提交=任务实际存在，盲重发=双派。加自证字段让读侧先查实际态。
            result["cancelled_run_note"] = ("cancelled 是 run 层状态（本 run 被新消息打断），"
                                            "不代表任务未创建——先 check_async_task 查该任务实际态，"
                                            "再决定是否重发（盲重发=双派）。")
        elif result.get("status") == "running":
            # r39t 静默信号（米娅验收单⑤）：Eve 洞1——超时+步数零增量才报疑似静默
            #（纯年龄会误伤正常慢步骤，误报多了米娅学会无视=设计白做）。
            prev = _LAST_STEPS.get(str(thread_id))
            _LAST_STEPS[str(thread_id)] = steps
            idle = None
            try:
                import datetime as _dt
                ua = str(run.get("updated_at") or "")
                if ua:
                    epoch = _dt.datetime.fromisoformat(ua.replace("Z", "+00:00")).timestamp()
                    idle = max(0, int((_dt.datetime.now(_dt.timezone.utc).timestamp() - epoch) / 60))
            except Exception:
                pass
            if idle is not None and idle >= 5 and prev is not None and steps == prev:
                # Eve 洞2：自证随包（步数零增量 prev→steps + 最后发言片段已脱敏）
                detail = f"（消息步数零增量 {prev}→{steps}，最后发言：{diag['last_snippet'] if diag else '无'}）"
                result["silent_warning"] = (f"疑似静默（run 已 {idle} 分钟无更新{detail}）——"
                                            "任务大概率卡死而非在跑，别等也别脑补，报管理员核查。")
        return result

    _asam._build_check_result = _bcr_with_guidance
except Exception as _e:
    print(f"[agent] check_async_task 报错指引补丁未生效（不影响启动）：{_e}", flush=True)

try:  # R68（Eve D1）：R66 分档挪家后旧节残留要出声，防"strict 被静默降成 auto_edit"这类暗坑（原 L157-162）
    from settings_mgr import load_settings as _ls_probe
    if "confirmLevel" in (_ls_probe().get("subagents") or {}):
        print("[agent] ⚠ 检测到旧节 subagents.confirmLevel 残留（现行为 general.confirmLevel）——旧值已忽略，请清理设置档防误导", flush=True)
except Exception:
    pass

# ── 包内模块（拆分后各归其位）──
from mia_agent.prompts import _system_prompt  # 原 L13-66
from mia_agent.sandbox import SandboxedShellBackend  # 原 L67-117
from mia_agent.confirm_gate import ConfirmGateMiddleware  # 原 L212-464（C1 过渡期：名单/判定真源仍被 confirm_gate_c1 引用）
from mia_agent.confirm_gate_c1 import ConfirmGateC1, assert_gate_order  # r41：官方 HITL 包装版（主图）；09-15 夜：连带启动保险丝
from mia_agent.flow_observer import observer as _flow_observer  # r41：流程体系 v2 观测器
from mia_agent.store import MiaState, _STORE  # 原 L120-122/L165-168/L804-854
from mia_agent.models import boss_model  # r34：_interrupt_on 空壳已拆
from mia_agent.plan_check import PlanCheckMiddleware  # r45 层2 验收导航/clarify/同型连撞
from mia_agent.tools import (_load_mcp_tools, dispatch_to_xiaoquan, edit_memory, email,  # 原 L171-210/L466-802
                             list_async_tasks, lark_send, manage_departments, search_knowledge_base,
                             dispatch_external, list_external_posts, list_external_results,
                             sd_generate, n8n)  # r58 对外派活一期; 09-16 +SD 本机出图; r39i +n8n 编排桥

# ── 包外：搜索/中间件（原 L125-127）──
from search_tools import web_search, web_search_bocha, web_search_tavily, web_search_metaso  # 原 L125
from scribe_hook import ScribeMiddleware  # 原 L126
from run_config import RunConfigMiddleware  # 原 L127

import skills_lock as _skills_lock  # 原 L999


# ── R59 官方多层架构：牛马编入部门（departments_config.json），部门主管图注册为
#    独立 graph（cow_graphs.py），米娅通过官方 AsyncSubAgent 五工具异步派活：
#    start/check/update/cancel/list——派活即回不阻塞，可中途转向/取消，任务状态
#    存专用 async_tasks 通道（防上下文压缩丢失）。──（原 L957-960）


def _load_departments():  # 原 L964-971
    # R69（Eve E1 双链）：唯一实现收进 cow_graphs，本模块函数级委托——两份读档=改一漏一的种子，拔掉。
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
            description=f"{d['name']}主管（牛马：{workers}）。接到部门任务后拆解派给牛马、验收汇总上交。",
            graph_id=d["slot"],
        ))
    # R64 总管层（爸爸的军事层级）：跨部门协同任务米娅转告总管，总管分解协调各部门
    out.append(AsyncSubAgent(
        name="总管",
        description="总管（任务分解官）。跨部门协同任务转告给他：他分解成各部门的活、协调各部门并行执行、汇总结果上交。单一部门的任务不用他。",
        graph_id="gm",
    ))
    # r25（hy4 A2.1 P1 修复）：主图此前没封 deepagents 自动注入的 general-purpose 影子子代理——
    # 它继承主图全工具却不带 ConfirmGate（deepagents/graph.py:751 注入条件 / :777 过滤自定义中间件），
    # 一次 task 批准=放出无门全权代理。照 cow_graphs 已验证的死胡同样板占领槽位（官方跳过条件=自带同名 spec）。
    # r39k（爸 09-29 令"简单问题派自身模型的子代理比启动牛马更快"）：该槽位从拒收站升级为
    # **同步轻量子代理**——继承米娅的模型（qwen-flash）、无独立线程/checkpointer（秒级派生），
    # tools 显式收窄为纯只读四件（同步子代理不经主图 ConfirmGate → 无危险动作可做=无门也安全，
    # r25 的洞不复发）；读文件类主脑自己更快（内置 read_file），落盘交付/长任务仍走部门牛马。
    from deepagents.middleware.subagents import SubAgent as _SyncSubAgent
    out.append(_SyncSubAgent(
        name="general-purpose",
        description="轻量快手（同步子代理，秒级）：简单查询、知识库检索、小分析、并列对比这类轻活用我。落盘交付/跨部门/长任务请派部门牛马。",
        system_prompt="你是米娅的轻量子代理：快、准、短。一次任务一答，答案直接可用；不确定就说明不确定，别铺摊子。",
        tools=[search_knowledge_base, list_async_tasks, list_external_posts, list_external_results],
    ))
    return out


_async_subagents = _build_async_subagents()  # 原 L994

# ── R10.3 skills_lock（Cora/NOVA 方案落地）：技能清单哈希锁——挂载回归保险 ──（原 L996-1009）
# 基线落 secrets 卷；不符=本组技能整体停用（宁可不带技能不裸奔）+日志+审计。
# 改挂载=必重启=必再校验，故启动校验覆盖回归场景；运行中宿主改文件到重启前不被捕获（诚实清单）。
_SKILLS_DIR = __import__("settings_mgr").workspace_root() / "skills"  # r37 贯通  # 原 L1000: Path(__file__).resolve().parent / "mia_home" / "skills"
if _skills_lock.enabled():
    _SKILLS_BAD = _skills_lock.verify(_SKILLS_DIR, _skills_lock.ensure_baseline(_SKILLS_DIR))
    if any(_SKILLS_BAD.values()):
        print(f"[skills_lock] 技能清单不符，本组技能已停用：{_SKILLS_BAD}（爸爸在设置页重新登记后重启）", flush=True)
        _SKILLS = []
    else:
        _SKILLS = ["skills/"]
else:
    _SKILLS = ["skills/"]


# ===== 官方对话压缩（deepagents SummarizationMiddleware，爸爸定调：功能用官方件）=====（原 L911-955）
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
    # R69（NOVA⚪/MK 教训）：压缩模型可配 interface.compaction.provider/model——
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
            backend=SandboxedShellBackend(root_dir=str(BASE / _WS_ROOT)),
            **kwargs,
        )]
    except Exception:
        return []  # 官方中间件不可用就不挂，绝不挡启动


# r25（hy4 A1.3 实证修复）：langchain_mcp_adapters 的 get_tools() 命名不带 mcp__ 前缀
# （库源码：原名或 server_name_tool.name）——门的 startswith 判定永不命中，MCP 工具会
# 降级为"口头重试放行"（潜在 P0）。修=装配时把 MCP 工具真名注入门的来源集合，按来源判定。
_mcp_tools = _load_mcp_tools()
ConfirmGateMiddleware._MCP_NAMES = {str(t.name).strip().lower() for t in _mcp_tools}

# 09-15 夜保险丝接线（主会话授权的最小接线，assert_gate_order 配套）：主图中间件先落具名变量，
# 编译前过一遍"ConfirmGateC1 确实在列"——漏装=启动炸，不许安全带装兜里（fail-closed，宁炸不静默）。
# 顺序约束：必须在上面 ConfirmGateMiddleware._MCP_NAMES 注入之后构造（门的 MCP 来源判定吃这份名单）。
_middleware = [
    ConfirmGateC1(),  # r41（C1）：官方 HITL 包装版四档门（批量卡/自包含拒出口）——替换现役 ConfirmGateMiddleware
    ScribeMiddleware(root_dir=BASE / _WS_ROOT),
    *_compaction_middleware(),
    RunConfigMiddleware(),  # 输入框的模型选择/联网开关在这里生效
    _flow_observer,  # r41 流程体系 v2 层3：动作序列观测（只记不拦）
    PlanCheckMiddleware(),  # r45 层2：验收导航注入+clarify 路由+同型×3 连撞提醒（09-13 夜窗）
]
assert_gate_order(_middleware)  # 现状语义=存在性检查（非顺序检查），缺门抛 ValueError 挡启动

agent = create_deep_agent(  # 原 L1011-1034
    model=boss_model,
    name="mia",
    # r34（CB 3.6）：官方 interrupt_on 参数拆除（R47 停用后恒空壳）——
    # 四档确认唯一实现=ConfirmGateC1 动态门（graph middleware 链内），改设置即时生效。
    system_prompt=_system_prompt(),  # 设置页 general.system_prompt 优先，_DEFAULT_PROMPT 只是出厂默认
    memory=["memory/MEMORY.md"],
    store=_STORE,  # R63 官方 store（PG 永久记忆）：跨线程共享，checkpointer 之外的全局记忆层
    skills=_SKILLS,  # R10.3 skills_lock：验证过的技能清单（不符=空列表整体停用）
    # R59：AsyncSubAgent 对象直接放进官方 subagents 参数（0.5.0 起同步/异步合并为单一参数，
    # deepagents 内部自动分流：同步→SubAgentMiddleware，异步→AsyncSubAgentMiddleware 五工具）
    subagents=_async_subagents,
    tools=[dispatch_to_xiaoquan, list_async_tasks, search_knowledge_base, edit_memory, manage_departments, email, n8n,  # R72 +邮箱托管; r48 M2 真工具; r39i +n8n 编排桥
           lark_send,  # r41 飞书桥（外发批准门内）
           dispatch_external, list_external_posts, list_external_results,  # r58 对外派活一期
           sd_generate,  # 09-16 本机 SD 出图（零成本不外网，无需批准门）
           *_mcp_tools, web_search, web_search_metaso, web_search_bocha, web_search_tavily],
    backend=SandboxedShellBackend(root_dir=str(BASE / _WS_ROOT)),
    state_schema=MiaState,
    middleware=_middleware,  # 09-15 夜：装配件提为具名变量交保险丝验身（内容与顺序逐字未动）
)

# r25（军事链断点3修复）：部门任务完工/受阻推送监视器——门放行 start_async_task 时登记
# {部门线程→主线程}，本监视器轮询到部门 run 结束就唤醒主线程转呈汇报（daemon 线程，幂等只启一次）。
from mia_agent import dept_watch as _dept_watch
_dept_watch.start()
