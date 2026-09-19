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
- **安全门禁**：防prompt注入、防密钥泄露
- **文件读写门禁**：必须先读文件才能写文件
- **治理网关**：所有工具调用过策略评估

我们做的是：
- **记忆使用门禁**：必须先读笔记才能做任务
- **工作日志强制**：任务完成必须写日志
- **灵敏度提升**：解决"该记不记、该看记录不看记录"

**核心区别：他们防危险，咱们防忘事。**

## 完整功能（当前 v1.3.2）

### 三层记忆结构
- **情景日志**：按天记录的原始事件流，schema v1 §2 frontmatter 条目（id/author/kind/significance/private/source/confidence/refs/open_question）
- **语义知识**：从日志抽象出来的规则、偏好、事实
- **程序手册**：可复用的工作流、操作指南
- **rolling handoff**（MVP·V1 Alice 案）：每 agent 一份 handoff.md，冷启动四行模板（在做/卡点/下一步/deadline），动手前第一眼就看它

### 门禁中间件（六条军规）
1. 硬拒，不是提醒
2. 同步+异步双钩
3. fail-closed
4. 拒信带正向出口
5. 只读白名单
6. 审计对账（§5 reason_code 稳定枚举 + JSONL 事件流）

### MCP Server 14个工具
| 工具 | 功能 |
|---|---|
| read_diary | 读笔记 |
| write_diary | 写日志（frontmatter 条目） |
| read_handoff | 读 rolling 交接（MVP 新增） |
| update_handoff | 更新 rolling 交接（MVP 新增） |
| gate_check | 收工前问一声 |
| diary_dashboard | 审计仪表盘 |
| diary_stats | 统计信息 |
| semantic_search | 向量语义搜索 |
| consolidate | 自动巩固 |
| list_pending_facts | 列出待审知识 |
| promote_fact | 晋升待审知识 |
| reject_fact | 删除待审知识 |
| export_diary | 导出日记包 |
| import_diary | 导入别人的日记包（指令模式扫描打 flag） |

### 三个宿主适配器
- **LangGraph版**：中间件类，双钩（同步+异步）
- **Claude版**：pretool-use hook（真实协议格式）
- **通用装饰器版**：@middleware.wrap，任何框架都能用

### 其他功能
- 向量语义搜索（理解意思，不是字面匹配；待审过滤双路：build 过滤+search 回查，v1.2.0）
- 索引内容指纹缓存（内容没变不重建，省 encode，v1.2.0）
- 自动巩固+晋升流（待审→晋升/拒绝）
- 导出导入（姐妹们互相分享经验；私密字段隔离）
- 审计仪表盘
- 回归测试 examples/test_regression_v120.py（恶意导入→关键词/向量都搜不到，防回归）

## 格式标准（schema v1）

智能体日记的**格式标准**：RC2 已按回票归纳（09-17 23:00 收票，若若五票全回），1.0 定稿外沿 09-20。

- 草案（RC2）：`docs/schema-v1-draft.md`
- 框架讨论轮输入：`docs/FRAMEWORK-2026-09-16.md`
- 差距分析与 MVP 改动清单：`docs/gap-analysis-schema-rc1-v120.md`

**MVP 已由爸爸拍板（2026-09-18）动工**——范围 = V1 Alice 案：情景日志 + rolling handoff，语义提取缓上。

## 验收（schema v1 §8 全单）

验收官跑单工具（七项机械判据）：

```bash
python -m agent_diary.lint <diary_base_dir>
# 退出码 0 = 七项全过
```

七项：① 字段完备 ② id 唯一排序 ③ canon 纯净 ④ private 不出门 ⑤ 状态位不互噬 ⑥ 门禁双路 ⑦ refs 完整性

## 快速开始

### 安装
```bash
pip install -r requirements.txt
```

### MCP Server（推荐）
```bash
AGENT_DIARY_HOME=/abs/path/to/diary python -m agent_diary.mcp_server
```

### 代码集成
```python
from agent_diary import DiaryStore, DiaryGate, make_diary_tools

store = DiaryStore("./diary_data")
gate = DiaryGate(store=store)
read_diary, write_diary = make_diary_tools(store, gate, session_id="user_123")
```

## 设计原则

1. **不是建议，是门禁**——不读笔记就不让调工具
2. **不是情绪记录，是工程记录**——事件+结果+教训
3. **不是翻本子，是触发式检索**——遇到问题自动搜
4. **不是私人日记，是团队共享**——一个人踩的坑全家都能学

## 与现有项目的区别

| 维度 | 现有记忆系统 | AgentDiary |
|---|---|---|
| 核心目标 | 防危险操作 | 防忘事、防重复踩坑 |
| 执行方式 | 事后检索 | 前置门禁+后置强制 |
| 触发机制 | 语义搜索 | 工具调用层硬拦截 |
| 适用场景 | 通用agent记忆 | 多智能体协作团队 |

## License

MIT
