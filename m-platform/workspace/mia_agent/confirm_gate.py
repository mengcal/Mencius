# -*- coding: utf-8 -*-
"""mia_agent/confirm_gate.py —— R74 权限门（参考成熟 agent 平台：范围×谨慎两轴，档位锁在带外）
拆分期注记：原 L212-464（拆分方案 #3）。
依赖：langchain（AgentMiddleware）；approvals / settings_mgr / langgraph.config /
langchain_core.messages 均在方法内懒加载（与原实现一致）。无包内依赖（独立中间件类）。
被引用：mia_agent/graph.py（middleware 列表，主层 new 一份；cow_graphs.py 经
agent_multimodel 兼容转发亦可取到本类——
差异注记：原 L214 的 `import os as _os` 在该段内从未被使用，拆分时删除。
"""
from langchain.agents.middleware.types import AgentMiddleware  # 原 L213

# 谨慎轴四档（R75 管理员定调"设置页 supreme"：档位=settings.general.confirmLevel 单源，       （原 L215-221）
# 设置页/顶栏快切同一真源，token 守写入；未配置/非法 fail-closed strict。旧带外文件地板已退役）：
#   plan      计划模式：只读工具放行，一切变更**硬拦**（不重试放行，助手只出方案给管理员看图纸）
#   strict    变更前确认：一切变更**软门**（每次改动停一下请示，管理员同意后重试放行一次）
#   auto_edit 自动编辑：改文件放行；执行代码/发信/动容器/编制等"越界级"变更仍软门请示
#   full      完全访问：不再请示（＝未来管理员开给助手的"管整机"档），但**自锁守卫仍在**——
#             她任何时候都改不动平台源码与档位文件本身（对标"我 full 访问 ZCode 却关不掉 ZCode 的完全访问"）
class ConfirmGateMiddleware(AgentMiddleware):  # 原 L222-459
    _pass_once: dict
    # 只读白名单（plan 档也只放行这些）；其余按"变更"处理。email 是读/写混合，按 args.action 细分。
    _READONLY = {"ls", "read_file", "glob", "grep", "search_knowledge_base",
                 "web_search", "web_search_metaso", "web_search_bocha", "web_search_tavily"}
    # auto_edit 档额外放行的"墙内可逆写"（编辑记忆/写工作文件），执行/发信/编制/派活/删除不放。
    _SOFTWRITE = {"write_file", "edit_file", "edit_memory"}
    # 自锁：这些路径/文件=她的"脑"和"锁"，任何档位（含 full/off）都不许她的工具写。纵深防御，
    # 真正的物理墙是源码 :ro 挂载 + 运行身份分离（下一步重构），此处先堵常规手。
    _SELFLOCK_TOKENS = (
        "agent_multimodel.py", "run_config.py", "office.py", "settings_mgr.py",
        "approvals.py", "mail_service.py", "cow_graphs.py", "providers.py",
        "checkpointer.py", "store.py", "search_tools.py", "scribe_hook.py", "vision.py",
        "agent.py", "langgraph.json", "departments_config.json", "rag_engine.py",
        "office.html", ".env", "Dockerfile", "docker-compose", "settings.json", ".settings_secrets",
        "control/mia_tier", "outer-workspace/control",
        # R80（评审A 配套补丁）：skills 是管理员给的技能（会进 system prompt），不是助手写的文件——
        # 物理面已 :ro 封死（写=EROFS），这里加自锁让助手先吃友好文案而不是裸报错
        "skills/", "SKILL.md",
        # R10.9（hy4 P1-3）：拆分后真实门代码在 office/ 包与 mia_agent/ 包里——
        # "office.py" 子串盖不住 office/app.py 等，"agent_multimodel.py" 只剩 17 行桩
        "office/", "office\\", "mia_agent",
    )
    _WRITE_TOOLS = {"write_file", "edit_file", "execute", "delete"}

    def __init__(self, sub_mode: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # R66 军事层级确认门（管理员拍板方案A）：主层(助手)=拦截后向管理员请示；
        # 子层(调度/组长/工人岗)=拦截后沿链上交请示，措辞不同、机制同款（软门：授权后重试放行一次）。
        self.sub_mode = sub_mode
        self._pass_once = {}  # {thread_id: {tool_name: 参数指纹}} —— 按对话隔离（评审B#7/评审A#6）；
                              # R10.2：口头路径也绑参数（hy4 ①-3），锚点表下沉 approvals（①-4）

    @staticmethod
    def _tid() -> str:
        try:
            from langgraph.config import get_config
            return str((get_config().get("configurable") or {}).get("thread_id", ""))
        except Exception:
            return ""

    @staticmethod
    def _level() -> str:
        # R75（管理员定调：设置页=唯一真源、自由选、凌驾一切，参考成熟 agent 平台 四档）：
        # 档位只读 settings.general.confirmLevel（设置页/顶栏快切都写这一个真源）。
        # 未配置/非法 → fail-closed strict（宁拦不放）。
        # "助手改不动档位"不靠文件地板限制管理员的选择，而靠：① 写端点要管理员 token（助手没有）；
        # ② execute 关沙箱后她物理上写不到 settings 文件（R75 下一步）。
        try:
            from settings_mgr import load_settings
            v = str((load_settings().get("general", {}) or {}).get("confirmLevel", "") or "").strip().lower()
            return v if v in ("plan", "strict", "auto_edit", "full", "off") else "strict"
        except Exception:
            return "strict"

    @staticmethod
    def _path_locked(name: str, args: dict | None) -> bool:
        """自锁守卫：写类工具若指向平台源码/档位/密钥=拦（任何档位，含 full/off）。"""
        if name not in ConfirmGateMiddleware._WRITE_TOOLS:
            return False
        blob = " ".join(str(v) for v in (args or {}).values()).lower()
        return any(tok.lower() in blob for tok in ConfirmGateMiddleware._SELFLOCK_TOKENS)

    @staticmethod
    def _decision(name: str, level: str, args: dict | None) -> str:
        """返回 'pass' | 'ask' | 'deny'。R74（评审A 洞2）：反选——非只读即变更，
        未知工具/mcp__*/edit_memory/delete 一律按变更处理，杜绝"名单漏网=fail-open"。"""
        if ConfirmGateMiddleware._path_locked(name, args):
            return "selflock"  # 由调用方给专用文案
        a = str((args or {}).get("action") or "").lower()
        if level in ("full", "off"):
            return "pass"
        # email 按动作分：只读动作并入只读集合
        ro = (name in ConfirmGateMiddleware._READONLY) or (name == "email" and a in ("", "list", "check", "read"))
        if level == "plan":
            return "pass" if ro else "deny"
        if ro:
            return "pass"
        # 到这里=非只读=变更（含 execute/write_file/edit_file/delete/edit_memory/
        # manage_departments/dispatch/start_async_task/task/email-send/任意 mcp__* 工具）
        if level == "strict":
            return "ask"
        if level == "auto_edit":
            if name in ConfirmGateMiddleware._SOFTWRITE:
                return "pass"  # 墙内可逆写放行
            return "ask"       # 其余变更（执行/删除/发信/编制/派活/MCP…）仍请示
        return "pass"

    def _prune(self):
        """R69（C 泄漏清理）：_pass_once 慢泄漏堵死——超 400 个对话键就裁到最新 200。"""
        if len(self._pass_once) > 400:
            for k in list(self._pass_once)[:200]:
                self._pass_once.pop(k, None)

    @staticmethod
    def _args_fp(args: dict | None) -> str:
        """R10（评审E P1-4）：调用参数指纹——外部批准绑定"被拦那次的参数"，Mia 批后换参数=重新拦截。
        稳定序列化（键排序）保证同一调用算出同一指纹；
        R10.2（hy4 ①-5）：异常回落在【本次进程】生成随机串——两次独立回落也几乎不可能相撞，
        彻底封死旧版 "?" 固定值下 "?"=="?" 的伪匹配。"""
        try:
            import hashlib as _hl
            import json as _j
            return _hl.sha256(_j.dumps(args or {}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        except Exception:
            import secrets as _s
            return _s.token_hex(8)

    @staticmethod
    def _args_preview(name: str, args: dict | None) -> str:
        """R10.3（评审B 🟡B 盲批）：拦截消息嵌入参数预览——管理员批的是【内容】不是工具名。
        execute 显命令头、write/edit 显目标路径、email 显收件人；去换行+截断防刷屏防排版注入。
        R10.4（评审C P3-2/评审D/评审B 三家同提"尾部盲区"）：超长 execute 命令改头尾拼合
        （头140+尾60）+ 尾注字符总数——"批头不批尾"的后段藏毒至少被提示"去看全量"。"""
        a = args if isinstance(args, dict) else {}
        try:
            import json as _jp
            if name == "execute":
                s = " ".join(str(a.get("command") or "").split())
                if len(s) > 200:
                    return f"{s[:140]}…{s[-60:]}（完整 {len(s)} 字符——请展开工具卡片核对全部参数）"
                return s
            elif name in ("write_file", "edit_file"):
                body = " ".join(str(a.get('content') or a.get('old_string') or '')[:80].split())
                s = f"{a.get('path') or a.get('file_path') or '?'} ← {body}"
            elif name == "email":
                s = f"to={a.get('to') or a.get('recipient') or '?'} subject={a.get('subject') or ''}"
            else:
                s = _jp.dumps(a, ensure_ascii=False)
            s = " ".join(str(s).split())
            if len(s) > 200:
                return f"{s[:200]}（完整 {len(s)} 字符——请展开工具卡片核对全部参数）"
            return s
        except Exception:
            return "(参数预览不可用)"

    def _block_msg(self, name: str, level: str, kind: str = "ask", args: dict | None = None) -> str:
        # R73（评审B🔴1）：工具名用「」框死——前端批准按钮正则靠括号取词。
        if kind == "selflock":
            return (f"🔒 「{name}」指向平台自身的守卫源码/档位/密钥——这是助手的「锁和脑」，"
                    "任何权限档都不允许她改（对标：作者 full 访问也关不掉 ZCode 的完全访问）。"
                    "需要改平台代码/档位，只能管理员或 ZCode 侧作者在宿主上动手。已拒绝。")
        if kind == "deny":
            head = f"⛔ 计划模式：变更类工具「{name}」被硬拦（此档只读，不出手）。"
        else:
            head = f"⛔ 确认档「{level}」已拦截工具「{name}」。"
        # R10.3（评审B 🟡B）：ask 类拦截一律带参数预览，管理员不用盲批
        if kind == "ask":
            head += f"\n【要执行的内容】{self._args_preview(name, args)}"
        if self.sub_mode:
            return (head + "你在军事链条内：立刻停止执行，把「要做什么/为什么/影响」写进工作结果"
                    "**上报上级请示**，由上级逐级向管理员求授权，不得自行重试绕过。（上级明确授权后重试会放行一次。）")
        if kind == "deny":
            return head + "请只出计划、不要动手；管理员切换档位后再来。"
        if self._needs_external(name):
            return (head + "这是需要管理员**亲口/亲点批准**的危险操作：请向管理员说明要做什么、为什么，"
                    "让管理员点本条拦截上的『批准』按钮（或在管理端批准）后再执行——**你自己反复重试不会放行**（批准权在管理员手里）。")
        return (head + "请立刻停止执行，先向管理员说明你要做什么、为什么，等他明确同意后重试（重试会放行一次）。")

    # R75（评审F F4/评审B）：这些"能提权/对外行动"的危险工具，ask 档**只认外部批准**
    # （管理员点拦截消息上的『批准』按钮 / token 打 /approvals），模型自己重试**不放行**——
    # 否则"重试即放"=批准权还在模型手里。数据区写（write_file/edit_file/edit_memory）仍可用口头重试放行。
    _NEEDS_EXTERNAL = {"execute", "delete", "email", "manage_departments",
                       "start_async_task", "dispatch_background_task", "task"}

    @staticmethod
    def _needs_external(name: str) -> bool:
        return name in ConfirmGateMiddleware._NEEDS_EXTERNAL

    def _gate(self, request, handler):
        """同步门。"""
        tc = getattr(request, "tool_call", None) or {}
        name = tc.get("name", "?")
        level = self._level()
        dec = self._decision(name, level, tc.get("args"))
        if dec == "pass":
            return handler(request)
        from langchain_core.messages import ToolMessage
        if dec == "selflock":
            return ToolMessage(content=self._block_msg(name, level, "selflock"), tool_call_id=tc.get("id", ""))
        if dec == "deny":  # 计划模式：硬拦，不给重试放行
            return ToolMessage(content=self._block_msg(name, level, "deny"), tool_call_id=tc.get("id", ""))
        # dec == "ask"：
        import approvals as _ap
        tid = self._tid()
        fp = self._args_fp(tc.get("args"))
        if _ap.consume(tid, name, fp):  # 外部批准（按钮/token）+ 参数指纹一致才放行（R10.2 hy4 ①-1）
            return handler(request)
        if self._needs_external(name) or name.startswith("mcp__"):
            # 危险工具/MCP 工具：无外部批准=不放行，重试也没用（批准权在管理员手里）；
            # 指纹登记进 approvals（全局共享，封 ①-4 跨实例锚点分裂）。
            # R10.3（评审B 🟡A）：fp 全文用〔fp:…〕机器可解析标记随消息给出——前端批准按钮
            # 原样带回，/approvals 与登记指纹比对，防"助手在管理员读消息与点按钮之间换参数"时窗调包。
            _ap.set_blocked(tid, name, fp)
            return ToolMessage(content=self._block_msg(name, level, "ask", tc.get("args"))
                + f"\n（本次调用指纹〔fp:{fp}〕：批准与参数绑定——换参数重试=批准作废、重新请示）",
                tool_call_id=tc.get("id", ""))
        # 数据区写类：口头重试放行一次（管理员在对话里说"好"即可）——R10.2 口头路径同样绑参数（hy4 ①-3），
        # 换参数=重新拦（无死循环：每次变更只需管理员再说一声好）
        passed = self._pass_once.setdefault(self._tid(), {})
        if passed.get(name) == fp:
            passed.pop(name)
            return handler(request)
        passed[name] = fp
        self._prune()
        return ToolMessage(content=self._block_msg(name, level, "ask", tc.get("args")), tool_call_id=tc.get("id", ""))

    async def _agate(self, request, handler):
        """异步门：放行分支必须 await（R52 教训）。"""
        tc = getattr(request, "tool_call", None) or {}
        name = tc.get("name", "?")
        level = self._level()
        dec = self._decision(name, level, tc.get("args"))
        if dec == "pass":
            return await handler(request)
        from langchain_core.messages import ToolMessage
        if dec in ("selflock", "deny"):
            return ToolMessage(content=self._block_msg(name, level, dec), tool_call_id=tc.get("id", ""))
        import approvals as _ap
        tid = self._tid()
        fp = self._args_fp(tc.get("args"))
        if _ap.consume(tid, name, fp):  # R10.2 与同步门同构：外部批准+参数指纹一致才放行
            return await handler(request)
        if self._needs_external(name) or name.startswith("mcp__"):
            _ap.set_blocked(tid, name, fp)
            return ToolMessage(content=self._block_msg(name, level, "ask", tc.get("args"))
                + f"\n（本次调用指纹〔fp:{fp}〕：批准与参数绑定——换参数重试=批准作废、重新请示）",
                tool_call_id=tc.get("id", ""))
        passed = self._pass_once.setdefault(self._tid(), {})
        if passed.get(name) == fp:
            passed.pop(name)
            return await handler(request)
        passed[name] = fp
        self._prune()
        return ToolMessage(content=self._block_msg(name, level, "ask", tc.get("args")), tool_call_id=tc.get("id", ""))

    def wrap_tool_call(self, request, handler):  # noqa: ANN001
        return self._gate(request, handler)

    async def awrap_tool_call(self, request, handler):  # noqa: ANN001
        return await self._agate(request, handler)


# （R79 评审E P3：此处旧有模块级 confirm_gate=ConfirmGateMiddleware() 实例，全仓零引用死码，已删——   （原 L462-463）
#   门实例由各图构造时各自 new，主层/子层参数不同，不存在全局单例。）
