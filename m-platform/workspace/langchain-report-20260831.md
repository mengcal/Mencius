# LangChain / LangGraph / DeepAgents 近况报告（2026年8月31日）

> 搜索时间窗口：2026年8月（近一周）
> 数据来源：PyPI 官方发布页 + GitHub Release + 中文技术社区综述
> 搜索受限说明：Web 直连 GitHub/官方文档多次超时，以下以 PyPI 官方数据为基准，社区文章补充背景

---

## 一、版本动态

### LangChain (Python)
| 版本 | 发布日期 | 备注 |
|---|---|---|
| **1.3.18** | 2026-08-27 | Latest stable |
| 1.4.0a1 | 2026-08-27 | Pre-release |
| 1.4.0a2 | 2026-08-28 | Pre-release |

**趋势**：LangChain 在 8 月底密集发布 1.4.0 alpha，预示大版本迭代。1.3.x 系列持续快迭代（6-8月已发 10+ 小版本），API 仍在频繁变动——升级需关注 breaking changes。

### LangGraph
| 版本 | 备注 |
|---|---|
| **0.13.2** | M 平台当前使用版本（授权版） |
| 0.13.x 系列 | 8 月持续迭代，重点在 streaming + MCP 集成 |

**注**：LangGraph 8 月具体 release notes 因网络超时未能拉取完整，但从社区文章确认 0.13 系列核心变化在 streaming 协议和 checkpointer 增强。

### DeepAgents
| 版本 | 发布日期 | 变更摘要 |
|---|---|---|
| **0.7.11** | 2026-08-28 | Latest — SDK integration hooks for rubric graders |
| 0.7.10 | 2026-08-28 | 同日双发 |
| 0.7.9 | 2026-08-25 | Disabled tracing inputs on middleware; RubricMiddleware 增强 |
| 0.7.8 | 2026-08-20 | — |
| 0.7.7 | 2026-08-18 | — |
| 0.7.6 | 2026-08-13 | — |
| 0.7.5 | 2026-08-06 | — |
| 0.7.4 | 2026-08-04 | — |
| 0.7.3 | 2026-08-03 | 同日连发 0.7.2/0.7.3 |

**8 月发布节奏**：密集（月内 10 个版本），说明 deepagents 正在快速迭代期。核心方向：
- **Rubric grading 中间件**（0.7.9-0.7.11）：评估/打分体系完善
- **中间件 tracing 控制**（0.7.9）：可关闭输入追踪，保护隐私/节省 token
- M 平台当前使用 **0.7.11**，与官方最新同步 ✅

---

## 二、MCP 集成趋势

根据 2026 年 Agent 框架横向对比文章（程序员食堂/知乎等），MCP 协议已成为 Agent 框架的**标配集成点**：

| 框架 | MCP 支持 |
|---|---|
| Google ADK | 原生支持 MCP |
| OpenAI Agents SDK | 原生支持 MCP |
| LangChain/LangGraph | 通过 `langchain-mcp-adapters` 包接入（M 平台已加） |
| Claude Agent SDK | 原生 MCP 支持 |

**对 M 平台的意义**：Dockerfile 里加的 `langchain-mcp-adapters` 依赖方向正确——LangChain 生态通过适配包接入 MCP 是官方路径，不是自研。米娅的 `_load_mcp_tools()` 从 settings 配置驱动加载，与官方模式一致。

**待办**：settings.json 的 `mcp.servers` 目前为空，需要爸爸配置具体 MCP 服务器（如 Tavily MCP、Filesystem MCP、Playwright MCP 等），米娅才会自动加载对应工具。

---

## 三、AsyncSubAgent / 多主管架构（M 平台已用）

M 平台当前架构（AsyncSubAgent + 部门层级 + supervisor-worker 分层）与 2026 年 Agent 框架趋势一致：

- **DeepAgents 0.5.0+**：同步/异步 SubAgent 合并到 `subagents=` 参数（M 平台已用此写法）
- **AsyncSubAgent 五工具**：start_async_task / check_async_task / update_async_task / cancel_async_task / list_async_tasks（状态通道 async_tasks）
- **层级架构**：supervisor → sub-supervisor → worker 多级分派（M 平台 departments_config.json 的 dept_0/dept_1/dept_2 + supervisor/worker 结构）

**社区验证**：2026 年多篇 Agent 框架对比文章（知乎"2026 AI Agent 框架实战对比"、CSDN"LangChain生态2026"）均确认 LangGraph + DeepAgents 的多级编排是主流方向，M 平台设计未跑偏。

---

## 四、M 平台兼容性建议

### ✅ 已对齐官方
1. deepagents 0.7.11（最新同步）
2. `subagents=` 参数（0.7 合并后写法）
3. AsyncSubAgent 五工具 + 状态通道
4. 部门图通过 LANGSERVE_GRAPHS env 注册（Docker 标准方式）
5. MCP 通过 langchain-mcp-adapters 接入（官方路径）
6. webhook reported 标记 + 并发锁（R58/R59 官方语义增强）

### ⚠️ 待关注
1. **LangChain 1.4.0 alpha**：大版本可能 breaking change，M 平台当前用 1.1.x/1.2.x（langchain-core 1.1.19），升级前需测试
2. **DeepAgents 快速迭代**：月内 10 版，关注 rubric grading 中间件是否可接入米娅的 ConfirmGate 4 档确认
3. **MCP 服务器未配置**：settings.json mcp.servers 为空，米娅有枪无子弹

### 🚫 不兼容风险（已规避）
- LangChain API 频繁迭代 → M 平台通过 agents_config.json + settings.json 抽象层隔离，切换 provider/model 不改代码 ✅
- deepagents subagents 参数变更 → 已通过 _build_async_subagents() 工厂函数封装 ✅

---

## 五、近一周关键事件时间线

| 日期 | 事件 |
|---|---|
| 2026-08-28 | deepagents 0.7.10/0.7.11 发布（rubric hooks） |
| 2026-08-27 | langchain 1.3.18 + 1.4.0a1 发布 |
| 2026-08-28 | langchain 1.4.0a2 发布 |
| 2026-08-25 | deepagents 0.7.9（middleware tracing 控制） |
| 2026-08-31 | M 平台 R59 收尾完成（折叠 + 防重锁 + 插件瘦身） |

---

*报告生成时间：2026-08-31 22:00 | 知夏 (Celia) 存档 | 搜索受限于 Web 通道，PyPI 数据为权威来源*