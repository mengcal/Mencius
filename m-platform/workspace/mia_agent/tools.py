# -*- coding: utf-8 -*-
"""mia_agent/tools.py —— 助手侧工具集
拆分来源：D:\\m\\workspace\\agent_multimodel.py 原 L171-210（dispatch_background_task）、
L466-552（edit_memory）、L555-702（manage_departments）、L706-727（_load_mcp_tools）、
L730-763（search_knowledge_base）、L766-801（email）（拆分方案 #6）。
依赖：langchain_core.tools（_tool 装饰器）、mia_agent.store._STORE（edit_memory 的 PG 镜像，
原文件里是模块级全局，见原 L544）；settings_mgr / mail_service / rag_engine / cow_graphs /
langchain_mcp_adapters / langgraph.config 等均在函数内懒加载（与原实现一致）。
路径注记：原代码用 `Path(__file__).resolve().parent`（monolith 与工作区同层）定位
mia_home / departments_config.json / settings.json；拆分后本模块位于工作区根下的
mia_agent/ 包内，工作区根 = 包目录上一级 = mia_agent.graph.BASE（BASE 按方案在 graph.py
定义）。为规避 tools↔graph 的 import 环，工具运行时经 _BASE() 懒加载取值。
被引用：mia_agent/graph.py（tools 列表，原 L1024-1025）、cow_graphs.py（经 agent_multimodel
兼容桩取 search_knowledge_base）。
"""
from langchain_core.tools import tool as _tool  # 原 L175

from mia_agent.store import _STORE  # edit_memory 的 PG 镜像用（原为同文件模块级全局，见原 L544）


def _BASE():
    """工作区根（原 agent_multimodel 的 parent）。BASE 在 mia_agent/graph.py 定义
    （= 包目录上一级）；此处调用时按需懒加载，规避 tools↔graph 顶层 import 环。"""
    from mia_agent.graph import BASE
    return BASE


# ── R3（2026-08-30）：派活工具化 + 干完自动汇报 ─────────────────────────（原 L171-174）
# 全官方机制：langgraph.config.get_config() 拿当前线程 id（官方运行时上下文），
# 后台 run 挂官方 webhook（runs.create 的 webhook 参数），完成后服务端主动 POST
# /tasks/webhook，由它在本对话线程 runs.create 唤醒助手汇报——对话线程零阻塞。


@_tool
def dispatch_background_task(task: str) -> str:  # 原 L179-209
    """把需要动手执行的任务派给后台后台任务队列异步执行（搜索调研/写代码/文件表格/识图/整理/跑脚本）。
    派完立即返回，不阻塞当前对话；任务完成后工作者会自动回到本对话汇报成果。
    task 必须自包含（后台线程看不到当前聊天记录），要写清目标、验收标准和涉及文件。"""
    try:
        from langgraph.config import get_config
        cfg = get_config() or {}
        conf = cfg.get("configurable") or {}
        main_thread = conf.get("thread_id", "")
        if conf.get("background_task_enabled"):
            return "你已在后台线程里。直接动手完成手头任务并给出结果，不要再派活（会无限套娃）。"
    except Exception:
        main_thread = ""
    import json as _json
    import os as _os
    import urllib.request as _ureq
    body = _json.dumps({"task": task, "main_thread": main_thread}).encode()
    # R80 续：dispatch 双钥匙门——进程内工具带 X-Internal-Key（WEBHOOK_TOKEN env，与 office 同源），
    # 沙箱/外部没这把 env=401（浏览器走 Bearer 管理员密钥）
    req = _ureq.Request("http://workplatform:8000/tasks/dispatch", data=body,
                        headers={"Content-Type": "application/json",
                                 "X-Internal-Key": _os.environ.get("WEBHOOK_TOKEN", "")})
    try:
        with _ureq.urlopen(req, timeout=15) as r:
            out = _json.load(r)
    except Exception as e:
        return f"派发失败：{e}"
    if out.get("ok"):
        return (f"已派给后台任务队列（单号 {out.get('id')}，队列 {out.get('queue','')}），"
                f"后台执行中，完成后自动回来汇报。现在可以继续陪管理员聊天。")
    return f"派发失败：{out.get('error')}"


@_tool
def edit_memory(action: str, section: str = "", content: str = "", project: str = "") -> str:  # 原 L467-552
    """管理你自己的长期记忆（Letta 式记忆自编辑）。
    action:
      read    读某个小节（section 填小节标题文字，不含 ##）；留空则返回全文目录
      append  向某小节追加内容（自动去重：完全相同的行不重复写）
      replace 整节替换（content 为该节新正文，## 标题自动保留）
      archive 把某小节移动到文末「已翻篇（历史）」区（过期记忆降权保留，不删除）
    project（可选）: 项目名。填了=读写该项目的专属记忆（与全局记忆分开存放，双层落位：
      本工具的 mia_home/memory/projects/<项目>.md 文件 + PG store ("memories","projects",<项目>) 分区）；
      留空 = 全局记忆 MEMORY.md（你的人设与跨项目铁律住这里）。
    规矩：长记忆是核心资产——append 前先 read 确认没有重复；只记事实与结论，不记流水账。
    section 示例（全局）：「管理员的偏好」「永不过时的铁律（血泪换的）」「已翻篇（历史，勿当现状）」；
    项目记忆的小节按项目写（如「关键决策」「遗留问题」「下次继续」）。"""
    import re as _re
    # R10.10（项目记忆分区，官方 BaseStore 层级 namespace 模式）：project 空=全局（恒 ("memories",)），
    # 非空=("memories","projects",<项目>) 分区，文件层落 mia_home/memory/projects/<项目>.md。
    # 项目名做路径安全白名单（拒 / \ .. 穿越字符）；项目记忆不进 system prompt（全局 MEMORY.md 才进），
    # 助手按需 read —— 全局人设记忆与项目工作记忆互不污染。
    project = (project or "").strip()
    if project and (_re.search(r'[\\/]', project) or '..' in project or len(project) > 64):
        return "project 名不合法（禁路径分隔符与 ..，最长 64 字符）"
    if project and (project.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
                    or any(ord(ch) < 32 for ch in project)):
        return "project 名不合法（Windows 保留名/控制字符——R10.11 评审C P3）"
    if project:
        _mem_name = f"projects/{project}.md"
        _mem_ns = ("memories", "projects", project)
    else:
        _mem_name = "MEMORY.md"
        _mem_ns = ("memories",)
    mem = _BASE() / "mia_home" / "memory" / _mem_name  # 原 L480: _Path(__file__).resolve().parent / "mia_home" / "memory" / _mem_name（拆分后经 _BASE() 取工作区根）
    if not mem.exists():
        # R70：首次写记忆=自动建档（旧版"文件不存在"硬错误已修）
        # R73 补丁（评审F/评审D 双双逮到）：退役角色卡时删了 _cid 赋值却漏改此行，
        # 全新环境首建记忆必 NameError——写死助手，并 CI 级 grep _cid 守门。
        mem.parent.mkdir(parents=True, exist_ok=True)  # R10.10：项目记忆落 projects/ 子目录
        mem.write_text((f"# 助手的记忆（{project}）" if project else "# 助手的记忆") + "\n\n", encoding="utf-8")
    raw = mem.read_text(encoding="utf-8")
    # 按 "## " 切小节：序言（首个 ## 前）+ [(标题, 正文)]
    parts = _re.split(r"(?m)^(## .+)$", raw)
    preamble = parts[0]
    sections = [(parts[i].strip().lstrip("#").strip(), parts[i + 1].strip("\n")) for i in range(1, len(parts) - 1, 2)]
    action = action.strip().lower()
    if action == "read":
        if not section:
            return "记忆目录（小节标题）：\n" + "\n".join("## " + t for t, _ in sections)
        for t, body in sections:
            if section in t:
                return f"【{t}】\n{body.strip()[:2000]}"
        return f"没有找到小节「{section}」。现有小节：\n" + "\n".join("## " + t for t, _ in sections)
    if action == "append":
        if not section or not content.strip():
            return "需要 section 和 content"
        new_lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
        for i, (t, body) in enumerate(sections):
            if section in t:
                # 去重时剥掉项目符号（"- xxx" 与 "xxx" 视为同一行，R48 修复）
                existing = [l.strip().lstrip("-").strip() for l in body.splitlines() if l.strip()]
                added = [l for l in new_lines if l.lstrip("-").strip() not in existing]
                if not added:
                    return "内容已存在（自动去重，未重复写入）"
                sections[i] = (t, body.rstrip() + "\n" + "\n".join("- " + l if not l.startswith("-") else l for l in added))
                break
        else:
            sections.append((section, "\n".join("- " + l for l in new_lines)))
    elif action == "replace":
        if not section or not content.strip():
            return "需要 section 和 content"
        for i, (t, _) in enumerate(sections):
            if section in t:
                sections[i] = (t, "\n" + content.strip() + "\n")
                break
        else:
            return f"没有找到小节「{section}」"
    elif action == "archive":
        target = next(((t, b) for t, b in sections if section in t), None)
        if not target:
            return f"没有找到小节「{section}」"
        sections = [s for s in sections if s != target]
        hist = next(((t, b) for t, b in sections if "已翻篇" in t), None)
        hist_title, hist_body = hist if hist else ("已翻篇（历史，勿当现状）", "")
        merged = hist_body.rstrip() + "\n\n### " + target[0] + "\n" + target[1].strip() if hist else "### " + target[0] + "\n" + target[1].strip()
        sections = [s for s in sections if "已翻篇" not in s[0]] + [(hist_title, merged)]
    else:
        return "action 只支持 read / append / replace / archive"
    # 写回 + 备份
    backup = mem.with_suffix(".md.bak")
    backup.write_text(raw, encoding="utf-8")
    out = preamble.rstrip() + "\n\n" + "\n\n".join(f"## {t}\n{b.strip()}" for t, b in sections) + "\n"
    mem.write_text(out, encoding="utf-8")
    # R63 官方 store 镜像：文件是 system prompt 加载源，store 是跨线程永久层（PG）。双写保证两处一致。
    # R68 修审计#6：_STORE 是同步 PostgresStore（513 行），旧代码 _aio.run(_STORE.aput) 调的是
    # 不存在的协程方法、又被裸 except 吞=镜像从未写进过 PG 还没人知道（"静默失败"反面教材）。
    # 现在直调 .put()，失败必须出声（文件已写成=主路径不受影响，但告警要看得见）。
    try:
        if _STORE is not None:
            import time as _time
            _STORE.put(_mem_ns, _mem_name,  # R10.10：全局=("memories",)，项目=("memories","projects",<项目>) 分区
                       {"content": out, "updated_at": _time.strftime("%Y-%m-%d %H:%M")})
        else:
            print("[memory] ⚠ PG store 缺失，本次未镜像（文件已写）", flush=True)
    except Exception as e:
        print(f"[memory] ⚠ PG store 镜像失败（文件已写，需排查）：{e}", flush=True)
    return f"✅ 记忆已更新（{action}）：{section or '全文'}。已自动备份上一版到 {mem.name}.bak"


@_tool
def manage_departments(action: str, department: str = "", name: str = "", desc: str = "", content: str = "") -> str:  # 原 L556-702
    """助手的人事权（R64，管理员 2026-09-01 授予）：随时增删工人岗、任命组长、给组长配工人岗。
    改 departments_config.json + 清部门图缓存，下次派活自动按新编制执行（零重启）。
    action:
      list              查看全部部门编制（组长/工人岗/槽位）
      add_department    新建部门（department=部门名，如"客服部"；自动分配空槽位）
      remove_department 解散部门（department=部门名）
      add_worker        招工人岗（department=部门名, name=工人岗名英文小写如translator, desc=职责一句话）
      remove_worker     开除工人岗（department=部门名, name=工人岗名）
      set_supervisor    任命/更换组长（department=部门名, name=组长名——从本部门工人岗提拔或新招）
      set_model         配模型（name=角色名如 boss/调度/coder；desc=服务商标注名；content=模型名）
    规矩：人事变动后跟管理员报备一声；工人岗名用英文小写；新工人岗自动继承本部门组长的模型配置；
    解散部门只解散编制不删历史对话。
    配模型原则（管理员定 2026-09-01）：平时一律便宜小模型（glm-4.5-air/书生免费）——
    助手分派、调度转告这类活小模型绰绰有余；只有管理员明说"这是大活"才临时升配大参数模型，
    干完立刻换回便宜模型（set_model 升降配你自己掌握，省钱第一）。工人岗优先免费。
    服务商标注名必须用设置页"外部连接"里已存在的，密钥不经过你（在设置页/secrets 里）。"""
    import json as _j
    # R64 权限开关接线（管理员质问"这个还是有效的吧"）：顶端"👑 助手无权"一键关闭人事权，
    # 之前只挡了设置页 agents 端点，manage_departments 绕过了它——现在补上。
    try:
        from settings_mgr import load_settings as _ls
        if not _ls().get("permissions", {}).get("miaManageAgents", True):
            return "⛔ 管理员已关闭助手管理工人岗的权限（顶栏 👑 开关），人事操作被拒。"
    except Exception:
        pass
    cfg_path = _BASE() / "departments_config.json"  # 原 L583: _Path(__file__).resolve().parent / "departments_config.json"（拆分后经 _BASE() 取工作区根）
    try:
        data = _j.loads(cfg_path.read_text(encoding="utf-8"))
        depts = data.get("departments") or []
    except Exception as e:
        return f"部门配置读取失败：{e}"
    action = action.strip().lower()

    def _find(name_):
        return next((d for d in depts if d.get("name") == name_), None)

    def _save():
        # R68 修 评审B🔴3：旧版只回写 departments，顶层 general_manager 节被整文件覆盖静默抹掉——
        # 先读旧档、只换 departments 键，其余顶层键（调度等）原样保留。
        try:
            old = _j.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        except Exception:
            old = {}
        if not isinstance(old, dict):
            old = {}
        old["departments"] = depts
        cfg_path.write_text(_j.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            import cow_graphs
            cow_graphs.invalidate_dept_cache()
        except Exception:
            pass

    if action == "list":
        out = []
        for d in depts:
            sup = (d.get("supervisor") or {}).get("name", "未任命")
            ws = "、".join(w.get("name", "") for w in (d.get("workers") or []))
            out.append(f"【{d.get('name')}】槽位 {d.get('slot')} · 组长 {sup} · 工人岗：{ws or '无'}")
        return "当前编制：\n" + "\n".join(out) if out else "还没有任何部门。用 add_department 新建。"
    if action == "add_department":
        if not department.strip():
            return "需要 department（部门名）"
        if _find(department.strip()):
            return f"部门「{department}」已存在"
        used = {d.get("slot") for d in depts}
        slot = next((f"dept_{i}" for i in range(4) if f"dept_{i}" not in used), None)
        if not slot:
            return "4 个槽位已满（dept_0..dept_3），请先解散一个部门"
        depts.append({"slot": slot, "name": department.strip(),
                      "supervisor": {"name": "supervisor", "role": "boss",
                                     "system_prompt": f"你是{department}组长。拆解任务、派给工人岗、汇总上交。"},
                      "workers": []})
        _save()
        return (f"✅ 已成立「{department}」（{slot}），部门图即时生效；"
                "⚠️ 助手的派活名单是启动时生成的——新部门要重启 workplatform 后才能被 start_async_task 派到"
                "（R68 修 评审B🔴4：如实相告不谎称立即可用）。用 add_worker 招人，招到人后用 set_supervisor 任命组长。")
    if action == "remove_department":
        d = _find(department.strip())
        if not d:
            return f"没有「{department}」这个部门"
        depts.remove(d)
        _save()
        return f"✅ 已解散「{department}」（历史对话保留）。"
    if action == "add_worker":
        d = _find(department.strip())
        if not d:
            return f"没有「{department}」这个部门"
        if not name.strip():
            return "需要 name（工人岗名，英文小写）"
        ws = d.setdefault("workers", [])
        if any(w.get("name") == name.strip() for w in ws):
            return f"「{name}」已是本部门工人岗"
        ws.append({"name": name.strip(), "role": name.strip(), "desc": desc.strip() or f"{d.get('name')}·{name.strip()}"})
        _save()
        return f"✅ 已招入「{name}」到{d.get('name')}（模型继承组长配置）。当前工人岗：{'、'.join(w['name'] for w in ws)}"
    if action == "remove_worker":
        d = _find(department.strip())
        if not d:
            return f"没有「{department}」这个部门"
        ws = d.get("workers") or []
        w = next((x for x in ws if x.get("name") == name.strip()), None)
        if not w:
            return f"{d.get('name')}里没有工人岗「{name}」"
        ws.remove(w)
        _save()
        return f"✅ 已开除「{name}」。剩余工人岗：{'、'.join(x['name'] for x in ws) or '无'}"
    if action == "set_supervisor":
        d = _find(department.strip())
        if not d:
            return f"没有「{department}」这个部门"
        if not name.strip():
            return "需要 name（组长名）"
        d.setdefault("supervisor", {})["name"] = name.strip()
        d["supervisor"].setdefault("role", "boss")
        _save()
        return f"✅ 已任命「{name}」为{d.get('name')}组长。"
    if action == "set_model":
        # R64 模型分配人事权：助手按管理员的活的大小给角色配模型（密钥不经过助手）
        from settings_mgr import load_settings, load_agents_config
        s = load_settings()
        pnames = [p.get("name") for p in (s.get("external", {}).get("providers", []) or []) if isinstance(p, dict)]
        if not name.strip():
            return f"需要 name（角色名：{'、'.join(load_agents_config().keys())}）"
        if desc.strip() not in pnames:
            return f"服务商标注「{desc}」不在设置页服务商列表（现有：{'、'.join(pnames)}）。请管理员先在设置页添加，或用现有标注。"
        cur = s.setdefault("agents", {}).setdefault(name.strip(), {})
        cur["provider"] = desc.strip()
        cur["model"] = (content or "").strip()
        # R79（评审E P3 注记）：此处直写 settings.json【合法绕过 HTTP token 门】——门在被绕处之前已设：
        # manage_departments 是危险工具，走到这行前必过 ConfirmGate 的外部批准（_NEEDS_EXTERNAL，
        # 管理员点『批准』/token 打 /approvals 才放行）；HTTP 写面（/settings/agents）另有 token 门。
        # 两门并联，工具链的钥匙=批准动作本身。agents 节无敏感键（凭据全在 secrets），整文件重写不泄密钥。
        (_BASE() / "settings.json").write_text(  # 原 L692: (_P(__file__).resolve().parent / "settings.json").write_text（拆分后经 _BASE() 取工作区根）
            __import__("json").dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        # 配置缓存刷新：下次派活/重建部门图按新模型跑
        try:
            import cow_graphs
            cow_graphs.invalidate_dept_cache()
        except Exception:
            pass
        return (f"✅ 角色「{name}」已配模型：{desc.strip()} / {content}。"
                f"下次该角色干活/部门重建时生效。")
    return "action 只支持 list / add_department / remove_department / add_worker / remove_worker / set_supervisor / set_model"


# ===== R58 MCP 生态接入（官方 langchain-mcp-adapters，settings mcp.servers 配置驱动）=====（原 L705）
def _load_mcp_tools():  # 原 L706-727
    """从 settings mcp.servers 加载 MCP 服务器工具。配置格式：
    mcp.servers = [{"name": "xxx", "url": "http://..."}]（streamable_http 传输）。
    无配置/加载失败 → 返回空列表，绝不挡启动。"""
    tools = []
    try:
        from settings_mgr import load_settings
        servers = (load_settings().get("mcp", {}) or {}).get("servers") or []
        if not servers:
            return []
        from langchain_mcp_adapters.client import MultiServerMCPClient
        import asyncio as _asyncio
        conf = {s["name"]: {"transport": s.get("transport", "streamable_http"), "url": s["url"]}
                for s in servers if isinstance(s, dict) and s.get("name") and s.get("url")}
        if not conf:
            return []
        client = MultiServerMCPClient(conf)
        tools = _asyncio.run(client.get_tools())
        print(f"[mcp] MCP 工具加载成功：{len(tools)} 个", flush=True)
    except Exception as e:
        print(f"[mcp] MCP 工具加载失败（忽略）：{e}", flush=True)
    return tools


@_tool
def search_knowledge_base(query: str, k: int = 5) -> str:  # 原 L731-763
    """查询管理员的知识库（RAG）。管理员入库的文档、日记、资料、配置都在里面。
    派活前、回答涉及管理员私人资料的问题前，先查这里，回答才有依据。
    k 为返回条数，默认 5。"""
    import json as _json
    import httpx as _httpx
    # R67（管理员 09-02 定）：嵌入模型唯一真源=配置页 rag.embeddingModel（单模型跨语言，qwen3 0.6b=1024维与表兼容）；
    # 不再按语言双模型分支——以后换向量模型，配置页改一个字段就行，代码零改动。
    try:
        from settings_mgr import load_settings, DEFAULT_EMBED_MODEL
        model = (load_settings().get("rag", {}) or {}).get("embeddingModel", "") or DEFAULT_EMBED_MODEL
    except Exception:
        from settings_mgr import DEFAULT_EMBED_MODEL
        model = DEFAULT_EMBED_MODEL
    # 嵌入：本机 Ollama（httpx 短超时，异常即报给助手）
    try:
        r = _httpx.post("http://host.docker.internal:11434/api/embed",
                        json={"model": model, "input": query[:4000]}, timeout=30)
        qv = r.json()["embeddings"][0]
    except Exception as e:
        return f"嵌入服务（本机 Ollama）不可用：{e}"
    try:
        # R69 双实现合并：检索 SQL 单一源在 rag_engine（与 office /rag/query 共吃一份）
        from rag_engine import search_vectors
        rows = search_vectors(qv, k)
        if not rows:
            return "知识库还是空的（管理员还没入库文档）。"
        out = "知识库检索结果（相关度降序）：\n"
        for name, text, score in rows:
            out += f"\n【{name} · 相关度 {float(score):.2f}】\n{text[:400]}\n"
        return out
    except Exception as e:
        return f"知识库查询失败：{e}"


# ── R72 邮箱托管（ClawEmail 两主账号归 M 平台，2026-09-03 管理员拍板）──────────（原 L766-767）
# 铁律继承 8/24 回信风暴：纯手动、单封、绝无自动回复/轮询/gateway（mail_service 里零守护线程）。
@_tool
def email(action: str, account: str = "", uid: str = "", to: str = "", subject: str = "", body: str = "") -> str:  # 原 L769-801
    """托管邮箱（ClawEmail）纯手动收发。
    action:
      list    列出注册邮箱（名字/地址/主账号归属/启停）
      check   看某邮箱最近来信（account=名字，如 example1/example2/home/work）
      read    读某封全文（account + uid=check 里的编号）
      send    发一封信（account + to + subject + body）——发信是对外变更，strict 档会先请示管理员
    铁律：①绝不自动回复——只回管理员明确让你回的信；②回信就用收信用的那个 account，地址用来信里的 From；
    ③一封一封来，禁止循环收发；④密钥/授权码永远不出现在信里和回复里。"""
    try:
        from settings_mgr import load_settings
        if not load_settings().get("permissions", {}).get("miaManageEmail", True):
            return "管理员已关闭助手管理邮箱的权限（permissions.miaManageEmail）——需要时转告管理员或作者开通。"
    except Exception:
        pass
    import mail_service
    try:
        if action == "list":
            accs = mail_service.accounts()
            return "注册邮箱：\n" + "\n".join(
                f"- {a['name']}｜{a.get('address','')}｜{a.get('label','')}｜{'启用' if a.get('enabled', True) else '停用'}"
                for a in accs) or "（空）"
        if action == "check":
            return mail_service.check(account)
        if action == "read":
            return mail_service.read(account, uid)
        if action == "send":
            if not (to and subject):
                return "send 需要 to 和 subject"
            return mail_service.send(account, to, subject, body)
        return "action 只支持 list / check / read / send"
    except Exception as e:
        return f"邮箱操作失败：{e}"
