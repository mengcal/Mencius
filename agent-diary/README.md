# AgentDiary 📔

**给智能体的工作日志系统——不是人类日记，是触发式记忆门禁**

> "你不读操作日记就想动手？不行，不给你权限。不写工作日志？算无效工作。"

## 这是什么？

AgentDiary 是一套**智能体工作日志强制执行系统**，解决两个核心痛点：

1. **该记不记**——智能体做完事就忘了，下次还踩同样的坑
2. **该看记录不看记录**——不读历史就动手，重复犯错

它不是人类日记（没有情绪、没有流水账），而是一套**工程化的记忆门禁**：
- **前置门禁**：不读笔记，不让你调执行类工具
- **后置门禁**：动完不写日志，不算完成任务

## 为什么我们是首创？

现有项目做的是：
- **安全门禁**：防prompt注入、防密钥泄露（Aegis/MemoryGuard）
- **文件读写门禁**：必须先读文件才能写文件（deer-flow ReadBeforeWriteMiddleware）
- **治理网关**：所有工具调用过策略评估（det-acp）

我们做的是：
- **记忆使用门禁**：必须先读笔记才能做任务
- **工作日志强制**：任务完成必须写日志
- **灵敏度提升**：解决"该记不记、该看记录不看记录"

**核心区别：他们防危险，咱们防忘事。**

## 三层记忆结构

### Layer 1: 情景日志（Episodic Log）
按时间记录的原始事件流，带显著性标记：
- 🔴 **关键**：爸爸铁律、关键决策、大坑、重要规律
- 🟡 **重要**：小坑、小决策、小任务
- ⚪ **普通**：不单独记，融入日常

### Layer 2: 语义知识（Semantic Facts）
从情景日志中抽象出来的规则、偏好、事实：
- 一条一个知识点（原子化）
- 结构化字段：fact/type/source/confidence
- 语义搜索：遇到相关问题自动检索

### Layer 3: 程序手册（Procedural Skills）
可复用的工作流、操作指南：
- 步骤化的操作指南
- 触发词：什么时候自动加载
- 比如："怎么发群邮件"

## 核心组件

### 1. memory_gate.py — 门禁中间件
```python
class MemoryGateMiddleware:
    """
    记忆门禁中间件——在工具调用层硬拦截：
    - 前置：调用执行类工具前，检查有没有读过笔记
    - 后置：任务结束时，检查有没有写过日志
    """
```

### 2. tools.py — 两个核心工具
- `read_diary(query)`：读笔记，语义搜索相关事件
- `write_diary(event, lesson, significance)`：写日志，记录事件和教训

### 3. store.py — 存储层
- 情景日志：Markdown文件，按天分文件
- 语义知识：SQLite数据库，结构化存储
- 向量索引：qwen3-embedding，语义检索

## 快速开始

```python
from agent_diary import MemoryGateMiddleware, DiaryStore

# 1. 初始化存储
store = DiaryStore("./diary_data")

# 2. 创建门禁中间件
gate = MemoryGateMiddleware(
    store=store,
    execution_tools=["run_command", "write_file", "send_email", "call_api"],
    read_before_execute=True,  # 不读笔记不能动手
    write_after_task=True,     # 动完必须写日志
)

# 3. 挂载到你的agent
agent = MyAgent(
    middlewares=[gate]
)
```

## 设计原则

1. **不是建议，是门禁**——不读笔记就不让调工具，不写日志就不算完成
2. **不是情绪记录，是工程记录**——记的是事件+结果+教训，不是心情
3. **不是翻本子，是触发式检索**——遇到相关问题自动搜，不是自己翻
4. **不是私人日记，是团队共享**——一个人踩的坑，全家都能学

## 与现有项目的区别

| 维度 | 现有记忆系统 | AgentDiary |
|---|---|---|
| 核心目标 | 防危险操作 | 防忘事、防重复踩坑 |
| 执行方式 | 事后检索 | 前置门禁+后置强制 |
| 记录内容 | 对话历史/摘要 | 事件+决策+教训 |
| 触发机制 | 语义搜索 | 工具调用层硬拦截 |
| 适用场景 | 通用agent记忆 | 多智能体协作团队 |

## Roadmap

- [x] MVP v0.1：read_diary + write_diary + 门禁中间件
- [x] v0.2：六条军规落地（硬拒/双钩/fail-closed/正向出口/白名单/审计对账）
- [x] v0.3：审计仪表盘（一行命令看门禁工作得好不好）
- [x] v0.4：搜索升级（关键词权重+显著性加权+时间衰减）
- [x] v0.5：完整demo更新
- [x] v0.6：三个必改级bug修复（celia实跑评审）
- [x] v0.7：MCP Server版！即插即用，所有MCP客户端都能接入
- [ ] 向量检索集成（qwen3-embedding）
- [ ] 多智能体共享（姐妹们互相看）
- [ ] 自动巩固（情景日志→语义知识的自动提取）

## MCP Server 使用方法（v0.7）

做成MCP Server，**所有支持MCP的agent都能即插即用**！

### 启动Server

```bash
python -m agent_diary.mcp_server
```

### 接入支持的客户端

- **Claude Desktop**：配置mcp.json，加一行就行
- **Cursor**：直接加MCP Server配置
- **任何支持MCP的框架**：都能接入

### 提供的工具

| 工具 | 功能 |
|---|---|
| `read_diary` | 读笔记，自动打标记 |
| `write_diary` | 写日志，自动打标记 |
| `diary_dashboard` | 审计仪表盘，看门禁工作得好不好 |
| `diary_stats` | 机器可读的统计摘要 |

### 提供的资源

- `diary://today`：今天的工作日志

### 提供的提示词

- `diary_gate_rules`：给agent的规则提示词

## v0.2 更新：六条军规

来自Mia C1/SubGate生产踩坑经验，全是踩出来的：

1. **硬拒，不是提醒**——工具根本不执行，不是"提醒一下"
2. **同步+异步双钩**——只写同步版上真服务必炸
3. **fail-closed**——门禁自己出错时默认拒，不是放
4. **拒信带正向出口**——告诉模型"那该怎么办"，不然原地重试烧圈
5. **只读白名单**——读笔记/写日志/纯查询先放行，不然死锁
6. **审计对账**——拦截数=0本身就是告警，说明门禁没生效

## License

MIT
