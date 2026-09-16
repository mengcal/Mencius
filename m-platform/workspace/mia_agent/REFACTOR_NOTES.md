# REFACTOR_NOTES — agent_multimodel.py（1034 行）拆分为 mia_agent/ 包

- 原文件（只读，未改动）：`D:\m\workspace\agent_multimodel.py`
- 产出目录：`D:\sandbox-workspace\scratch\refactor\mia_agent\`（8 个 .py）+ 部署桩 `D:\sandbox-workspace\scratch\refactor\agent_multimodel.py`
- 拆分日期：2026-09-06；验证：`python -m py_compile`（Python 3.10.6）全部通过

## 一、目录结构与依赖方向

```
D:\sandbox-workspace\scratch\refactor\
├── agent_multimodel.py        # 部署桩：转发 agent + cow_graphs 兼容名（见第五节）
└── mia_agent\
    ├── __init__.py            # 承接原模块 docstring；刻意零副作用（不在此 import graph）
    ├── prompts.py             # 无包内依赖
    ├── sandbox.py             # 无包内依赖
    ├── confirm_gate.py        # 无包内依赖（独立中间件，只依赖 langchain）
    ├── store.py               # 无包内依赖（deepagents/typing）
    ├── models.py              # 无包内依赖（providers/settings_mgr）
    ├── tools.py               # → mia_agent.store（顶层）；→ mia_agent.graph.BASE（函数内懒加载）
    └── graph.py               # → 上述全部 + search_tools/scribe_hook/run_config/skills_lock
```

依赖单向：`prompts/sandbox/confirm_gate/store/models → tools → graph`，无环。
`settings_mgr` 按原实现继续在函数内懒加载（各模块同款），未提升为顶层依赖。

## 二、拆分对照表（原行号 → 新文件）

| 原行号 | 内容 | 去向 |
|---|---|---|
| L1-9 | 模块 docstring | `__init__.py` |
| L10 | `import json`（顶层，全文件未用） | 删除（死码，见第四节） |
| L11 | `from pathlib import Path` | `graph.py` |
| L13-66 | `_DEFAULT_PROMPT` + `_system_prompt()` | `prompts.py`（方案 #1） |
| L67 | `from deepagents import create_deep_agent, SubAgent` | `graph.py`（`SubAgent` 全文件未用，删除） |
| L68-70 | `LocalShellBackend` / `ExecuteResponse` / `import os` | `sandbox.py` |
| L72-117 | `SandboxedShellBackend` | `sandbox.py`（方案 #2） |
| L120-122 | `DeepAgentState` / `Annotated` / `NotRequired` | `store.py` |
| L124 | `from providers import make_model` | `models.py` |
| L125 | `from search_tools import web_search…` | `graph.py` |
| L126-127 | `ScribeMiddleware` / `RunConfigMiddleware` | `graph.py` |
| L130-155 | cow_task SDK monkey-patch（ThreadsClient.create 打标签） | `graph.py` 顶部（方案规定：全局副作用只执行一次） |
| L157-162 | confirmLevel 旧节残留探测 | `graph.py` 顶部（同上，模块级副作用） |
| L165-168 | `_merge_mia` | `store.py`（方案 #4） |
| L171-210 | R3 注释 + `_tool` import + `dispatch_to_xiaoquan` | `tools.py`（方案 #6） |
| L212-464 | `ConfirmGateMiddleware`（含 L213 AgentMiddleware import、L215-241 常量、全部方法） | `confirm_gate.py`（方案 #3） |
| L462-463 | R79 死码注记（旧全局 confirm_gate 实例已删） | `confirm_gate.py` 尾注 |
| L466-552 | `edit_memory` | `tools.py`（`_STORE` 改从 `store.py` import；路径经 `_BASE()`） |
| L555-702 | `manage_departments` | `tools.py`（路径经 `_BASE()`） |
| L706-727 | `_load_mcp_tools` | `tools.py` |
| L730-763 | `search_knowledge_base` | `tools.py` |
| L766-801 | `email` | `tools.py` |
| L804-806 | `MiaState` | `store.py` |
| L808-816 | `BASE` / `MEMORY_FILE` 建档 | `graph.py`（方案未单列；因 BASE 按方案在 graph.py 定义，建档副作用随行） |
| L819-854 | `_STORE_CM` / `_make_store` / `_STORE` | `store.py` |
| L858-861 | `load_agents_config` import + `_CFG` | `models.py`（方案 #5） |
| L864-880 | `_model` | `models.py` |
| L883-890 | `_global_params` | `models.py` |
| L893-901 | `boss_model` 构造（含 R49 注记） | `models.py`（在方案 #5 行号段内；graph.py 经 import 取用） |
| L904-908 | `_interrupt_on` | `models.py` |
| L911-955 | `_compaction_middleware` | `graph.py`（方案未单列；属装配件，依赖 boss_model/BASE/SandboxedShellBackend） |
| L957-961 | R59 注释 + `AsyncSubAgent` import | `graph.py` |
| L964-994 | `_load_departments` / `_build_async_subagents` / `_async_subagents` | `graph.py` |
| L996-1009 | skills_lock 校验块（`_SKILLS_DIR`/`_SKILLS`） | `graph.py`（`_SKILLS_DIR` 改用 BASE） |
| L1011-1034 | `agent = create_deep_agent(...)` 装配 | `graph.py` |
| 原文件本体 | 部署后只剩转发 | 见第五节桩文件 |

## 三、路径语义变化（关键）

- 原 monolith 与工作区同层，`Path(__file__).resolve().parent` 即工作区根；
  拆分后包在工作区根下一级，故 **`BASE = Path(__file__).resolve().parent.parent`（在 `graph.py` 定义）**，
  与原值等价——前提是部署时 `mia_agent/` 位于工作区根（`D:\m\workspace\mia_agent\`）。
- `tools.py` 的三处工作区路径（edit_memory 的 `mia_home/memory/MEMORY.md` 原 L480、
  manage_departments 的 `departments_config.json` 原 L583、set_model 的 `settings.json` 原 L692）
  改经 `_BASE()` 在**调用时**从 `mia_agent.graph` 懒加载取 BASE——避免 tools↔graph 顶层 import 环
  （graph 顶层 import tools）。工具运行时 graph 必已装配完成，取值必然成功。
- `_SKILLS_DIR`（原 L1000）、`MEMORY_FILE`（原 L810）、backend/Scribe 的 `root_dir`（原 L951/L1026/L1030）
  均随 BASE 定义落在 `graph.py`，语义不变。

## 四、与原文的有意差异（全部为拆分必需或死码清理，未改任何行为逻辑）

1. **删除未用 import（死码）**：原 L10 `import json`（顶层，全文件 0 引用）；原 L67 `SubAgent`；
   原 L214 `import os as _os`（该段内 0 引用）；edit_memory/manage_departments/set_model 内的
   `from pathlib import Path as _Path/_P`（路径改经 `_BASE()` 后 0 引用）。
2. **`from mia_agent.store import _STORE`**（tools.py 顶层）：替代原同文件模块级全局 `_STORE`（原 L544 引用点不变）。
3. **路径改经 `_BASE()`**（见第三节），原行以行尾注释标明改法。
4. **BASE 由 `parent` 改 `parent.parent`**（graph.py，方案规定），部署到位后取值不变。
5. **MEMORY_FILE 段（L808-816）与 `_compaction_middleware`（L911-955）归 graph.py**：方案条目未单列，
   按依赖归属就近落位（均依赖 BASE/boss_model 等装配上下文）。
6. **boss_model 构造（L893-901）落 models.py**：在方案 #5 行号段内；graph.py `from mia_agent.models import boss_model`。
7. **import 位置重排**：原 L120-127 的包外 import 按用途分流到 store/models/graph；加载顺序差异不影响行为
   （各模块顶层无相互依赖，副作用时点与原实现等价：全部发生在 `import mia_agent.graph` 期间）。
8. 各文件新增 `# 原 Lxx` 行号锚点注释与模块 docstring（纯注释，不改变执行语义）。

## 五、部署桩与兼容转发（重要偏离说明）

方案要求"原文件留一行 `from mia_agent.graph import agent`"。但全仓 grep 显示 **不止 `agent` 一个名字被外部引用**：

| 引用点 | 引用名 |
|---|---|
| `agent.py:7`、`office/app.py:30` | `agent` |
| `cow_graphs.py:59`、`cow_graphs.py:275` | `SandboxedShellBackend` |
| `cow_graphs.py:68`、`cow_graphs.py:275` | `ConfirmGateMiddleware`、`search_knowledge_base` |

只留一行会让 cow_graphs 三处 ImportError。故桩文件（`scratch/refactor/agent_multimodel.py`）=
方案一行 + 3 个兼容转发（均 `noqa: F401`）。**本次未改动 D:\m 下任何文件**（无写权限）；
部署时：① 把 `mia_agent/` 拷到 `D:\m\workspace\mia_agent\`；② 用桩覆盖 `D:\m\workspace\agent_multimodel.py`。

无环性复核：cow_graphs 对 agent_multimodel 的引用全在函数内（其源码注释"函数内引避免顶层环"），
而 graph.py 对 cow_graphs 的引用也只在 `_load_departments`/manage_departments 内懒加载——
与拆分前等价，启动链 agent_multimodel → mia_agent.graph 不经 cow_graphs 顶层。

## 六、验证

- `python -m py_compile`（Python 3.10.6，支持原码 `int | None` 语法）对 8 个包文件 + 桩全部通过。
- 未做运行时验证（本机无 deepagents/langgraph/settings_mgr 等平台依赖与 DATABASE_URI 环境）；
  首次部署后建议观察启动日志中 `[mcal]`、`[mcp]`、`[skills_lock]`、`[compaction]` 各印签是否与拆分前一致。
