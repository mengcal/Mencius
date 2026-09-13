# -*- coding: utf-8 -*-
"""scribe_hook.py — 书记员旁路（官方 AgentMiddleware 实现，2026-08-28 知夏）

为什么存在：米娅提示词里写了"动手前查笔记、干活随手记"，但她经常忘。
靠提示词自觉 = 靠不住；改成程序层强制钩子，她想忘都忘不掉。

设计原则（爸爸的铁律：不要越改越糟糕 → 不卡顿、可禁用、绝不影响主流程）：
1. 提醒是固定文案注入，记录是确定性追加写文件，不卡主流程
2. wrap_tool_call 官方钩子：在工具执行前后插入行为，工具本身逻辑零改动
3. 任何钩子内异常都吞掉（log 到 auto_log.md 的 error 行），绝不打断米娅干活
4. 可通过 settings 的 scribe.enabled=false 整体禁用（运行时读，改设置即生效）

行为：
- 每轮对话（agent run）第一次工具调用前：在工具结果里注入"查笔记"提醒
  （选第一次而不是每次，避免刷屏浪费上下文）
- 每次工具调用后：把 工具名+参数摘要+结果摘要 追加到 mia_home/notes/auto_log.md
  —— 这就是"概略记录"，米娅事后整理正式笔记的素材

R51 新增（Mem0 式事实抽取 + notes aging，爸爸 2026-08-31 拍板）：
- 事实抽取：模型回复累积 >600 字 → 后台线程调书生 intern-latest（月免费 9000 万，
  不占日额度）抽取结构化事实 → 追加到 mia_home/memory/facts-YYYY-MM.md（带 [MM-DD] 时间戳，
  行级去重）。后台线程不阻塞对话。
- notes aging：每天一次扫描 notes/**/*.md（排除 auto_log/aging_report/共享区），
  超 30 天未动的写进 notes/aging_report.md 建议归档（只报告不动文件，安全）
"""
import threading
import time
from datetime import datetime, date
from pathlib import Path

from langchain.agents.middleware.types import AgentMiddleware

try:
    from settings_mgr import load_settings
except Exception:  # 老环境兜底：没有 settings_mgr 就默认启用
    def load_settings():
        return {}

# r2-1（09-12 基线 C3 案）：REMINDER 常量退役——工具结果注入面曾污染"原样抄写"
# 类任务产物，提醒统一走 WORK_RULES_INJECT（system 侧每轮注入）。

# R64 工作规范强制注入（每轮 system prompt 尾部，模型必读）——
# 规范正文在 mia_home/notes/工作规范.md（可查询），这里是每轮强制的执行令。
WORK_RULES_INJECT = (
    "\n\n【本轮工作规范（书记员强制执行令，先于一切动作）】\n"
    "1. 动手前先查笔记：execute 跑 notes search 关键词（或看 mia_home/notes/工作规范.md），"
    "有记录照做，绝不凭记忆瞎干。\n"
    "2. 派活纪律：凡动手的活一律 start_async_task 转告总管，把爸爸原话完整转达，"
    "自己不拆解不执行不等结果；只有纯聊天/常识问答才直接回答。\n"
    "3. 人事指令（招/开除牛马、成立/解散部门、任命主管）→ manage_departments 直接执行，完事跟爸爸报备。\n"
    "4. 干完关键步骤：让书记员记笔记（auto_log 已自动记，重要结论手动补一笔）。\n"
    "5. 违反以上任何一条 = 失职。"
)

# ── R51 事实抽取节流与缓冲 ──
_EXTRACT_THRESHOLD = 600      # 累积字数触发抽取
_EXTRACT_MIN_INTERVAL = 300   # 两次抽取最小间隔秒
_AGING_DAYS = 30              # 笔记 aging 阈值（天）


def _enabled() -> bool:
    try:
        return bool(load_settings().get("scribe", {}).get("enabled", True))
    except Exception:
        return True


def _fact_extract_enabled() -> bool:
    try:
        return bool(load_settings().get("scribe", {}).get("factExtract", True))
    except Exception:
        return True


class ScribeMiddleware(AgentMiddleware):
    """书记员旁路：before-run 提醒 + per-tool 概略记录 + 事实抽取 + notes aging。"""

    def __init__(self, root_dir: str | Path):
        self._root = Path(root_dir)
        self._log_file = self._root / "notes" / "auto_log.md"
        self._buf: list[str] = []          # R51 待抽取的对话片段
        self._buf_lock = threading.Lock()
        self._last_extract = 0.0           # epoch 秒

    # ---- R64 工作规范强制注入（爸爸定调：书记员提醒必须成为强制提示词）----
    # 老方式把提醒贴在工具结果尾部 = 软建议，米娅可以当耳旁风；
    # 新方式：每轮模型调用前把工作规范注入 system prompt 尾部——模型每轮必读，想忘都忘不掉。
    def _inject_work_rules(self, request):
        try:
            sp = getattr(request, "system_prompt", "") or ""
            request.system_prompt = sp + WORK_RULES_INJECT
        except Exception:
            pass

    # ---- R51：模型调用钩子——收集 AI 回复做事实抽取素材 + 强制注入工作规范 ----
    def wrap_model_call(self, request, handler):
        if _enabled():
            self._inject_work_rules(request)
        result = handler(request)
        if _enabled() and _fact_extract_enabled():
            try:
                self._collect(result)
            except Exception:
                pass
        return result

    async def awrap_model_call(self, request, handler):
        if _enabled():
            self._inject_work_rules(request)
        result = await handler(request)
        if _enabled() and _fact_extract_enabled():
            try:
                self._collect(result)
            except Exception:
                pass
        return result

    def _collect(self, result):
        text = self._result_text(result)
        if not text:
            return
        with self._buf_lock:
            self._buf.append(text[:1500])
            total = sum(len(t) for t in self._buf)
        now = time.time()
        if total >= _EXTRACT_THRESHOLD and now - self._last_extract >= _EXTRACT_MIN_INTERVAL:
            with self._buf_lock:
                batch = "\n".join(self._buf)[-4000:]
                self._buf.clear()
            self._last_extract = now
            threading.Thread(target=self._extract_facts, args=(batch,), daemon=True).start()

    # ---- R51：后台事实抽取（fire-and-forget；R64 去硬编码，按角色从设置页解析）----
    def _extract_facts(self, batch: str):
        try:
            from providers import make_model
            from settings_mgr import load_agents_config
            _ac = load_agents_config()
            _fc = _ac.get("archivist") or _ac.get("scribe") or _ac.get("boss") or {}
            m = make_model(_fc.get("provider", ""), _fc.get("model", ""))
            prompt = (
                "从下面的对话片段中抽取值得长期记住的事实（人物关系/爸爸的偏好/配置变更/重要结论/账号额度）。\n"
                "每条一行，格式：- [今天] 事实（简洁、可独立理解）。没有值得记的就只输出 NONE。\n\n对话片段：\n" + batch)
            r = m.invoke(prompt)
            text = str(getattr(r, "content", "")).strip()
            if not text or text.upper().startswith("NONE"):
                return
            today = datetime.now().strftime("%m-%d")
            facts_file = self._root / "memory" / f"facts-{datetime.now().strftime('%Y-%m')}.md"
            facts_file.parent.mkdir(parents=True, exist_ok=True)
            existing = facts_file.read_text(encoding="utf-8") if facts_file.exists() else ""
            added = 0
            with open(facts_file, "a", encoding="utf-8") as f:
                for line in text.splitlines():
                    line = line.strip().lstrip("-").strip()
                    if not line or line.upper() == "NONE":
                        continue
                    entry = f"- [{today}] {line}"
                    if entry in existing or line in existing:
                        continue  # 行级去重
                    f.write(entry + "\n")
                    existing += entry + "\n"
                    added += 1
            if added:
                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(f"- `{datetime.now().strftime('%m-%d %H:%M:%S')}` **事实抽取** 抽到 {added} 条 → memory/facts 文件\n")
        except Exception:
            pass  # 抽取失败绝不影响主流程

    # ---- R51：notes aging（每天一次，只报告不动文件）----
    def _aging_report(self):
        try:
            state_f = self._root / "notes" / ".aging_last"
            today = date.today().isoformat()
            if state_f.exists() and state_f.read_text(encoding="utf-8").strip() == today:
                return
            notes_dir = self._root / "notes"
            if not notes_dir.exists():
                return
            stale = []
            now_ts = datetime.now().timestamp()
            for p in notes_dir.rglob("*.md"):
                rel = str(p.relative_to(notes_dir))
                if any(k in rel for k in ("auto_log", "aging_report", "owui_shared", "owui_archive")):
                    continue
                if now_ts - p.stat().st_mtime > _AGING_DAYS * 86400:
                    stale.append(rel)
            if stale:
                rpt = notes_dir / "aging_report.md"
                with open(rpt, "a", encoding="utf-8") as f:
                    f.write(f"\n## {today} aging 巡检\n以下笔记超 {_AGING_DAYS} 天未更新，建议归档或复核：\n")
                    for s in stale:
                        f.write(f"- {s}\n")
            state_f.write_text(today, encoding="utf-8")
        except Exception:
            pass

    # ---- 核心钩子：包住每一次工具调用 ----
    # 注意：langgraph-api 是异步运行（astream），官方要求异步上下文必须实现 awrap_tool_call，
    # 只写同步版会 NotImplementedError（2026-08-29 踩坑）。两个版本保持同一逻辑。
    def wrap_tool_call(self, request, handler):  # noqa: ANN001
        if not _enabled():
            return handler(request)
        self._aging_report()  # 每天首次工具调用顺带跑一次 aging 巡检（异常内部吞）
        name = (request.tool_call or {}).get("name", "?")
        result = handler(request)  # 先正常干活，钩子绝不挡路
        try:
            self._log(name, (request.tool_call or {}).get("args"), result)
        except Exception:
            pass  # 记账失败不能影响干活
        # r2-1（09-12 基线 C3 实锤）：不再把提醒拼进工具返回值——"原样抄写"类任务
        # 会把 REMINDER 当文件正文抄进产物。规范强制令已由 awrap/before_model 的
        # WORK_RULES_INJECT 走 system 侧每轮注入（R64 正解），工具结果面保持零污染。
        return result

    async def awrap_tool_call(self, request, handler):  # noqa: ANN001
        if not _enabled():
            return await handler(request)
        self._aging_report()
        name = (request.tool_call or {}).get("name", "?")
        result = await handler(request)
        try:
            self._log(name, (request.tool_call or {}).get("args"), result)
        except Exception:
            pass
        # r2-1：同 wrap_tool_call——提醒走 system 侧（WORK_RULES_INJECT），
        # 工具返回值零污染（09-12 基线 C3 抄写污染案）。
        return result

    # ---- 概略记录：一行工具调用 + 结果摘要，追加写 ----
    def _log(self, name: str, args, result):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        args_s = str(args)[:120] if args else ""
        res_s = self._result_text(result)[:200]
        ts = datetime.now().strftime("%m-%d %H:%M:%S")
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(f"- `{ts}` **{name}** `{args_s}`\n"
                    f"  - {res_s}\n")

    def _result_text(self, result) -> str:
        content = getattr(result, "content", result)
        if isinstance(content, list):  # 多模态 content 块
            content = " ".join(
                str(c.get("text", "")) if isinstance(c, dict) else str(c)
                for c in content)
        return str(content).replace("\n", " ").strip()
