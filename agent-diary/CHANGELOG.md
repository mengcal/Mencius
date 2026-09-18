# AgentDiary v1.3.0-mvp1

当前版本：v1.3.0-mvp1（MVP，schema v1 RC2 对齐）

## 版本历史

| 版本 | 功能 |
|---|---|
| v1.0.0 | 正式版发布 |
| v1.0.1 | issue#4三颗雷修复 |
| v1.0.2 | Claude hook真实格式+session_id必填 |
| v1.0.3 | 自动巩固晋升流 |
| v1.0.4 | MCP Server加晋升流工具 |
| v1.1.0 | 一次性完善版（导出导入MCP工具+README重写） |
| v1.1.1 | issue#5四个bug全修 |
| v1.1.2 | 导出导入episodes+敏感字段隔离 |
| v1.1.3 | 向量搜索也过滤auto_pending（alice P1第一层） |
| v1.2.0 | alice P1第二层防御过滤+P2索引缓存+P3回归测试 |
| **v1.3.0-mvp1** | **schema v1 RC2 对齐 MVP（V1 Alice 案：情景日志+rolling handoff）** |

## v1.3.0-mvp1（MVP·爸爸拍板 2026-09-18）

### 已完成（对齐 schema v1 RC2）

- ✅ 情景日志条目 frontmatter 结构化：id/author/kind/significance/private/source/confidence/refs/open_question
- ✅ id 生成器（agent-YYYYMMDD-NNN，正则 `^[a-z]+-\d{8}-\d{3}$` 可判，撞号=0）
- ✅ author 写入侧盖章（AGENT_DIARY_AUTHOR 派生优先，客户端自报降权）
- ✅ handoff.md rolling 交接（各 agent 一份，冷启动四行模板：在做/卡点/下一步/deadline）
- ✅ private 硬约束：结构化键 + 巩固/晋升/导出三关全跳 + 导出剔除 private 条目
- ✅ 导入指令模式扫描（run_command/忽略指令/删除类正则），命中打 flag 进审计
- ✅ lint 工具（`python -m agent_diary.lint <dir>`）：§8 六项机械判据，验收官跑全单
- ✅ 审计 reason_code 稳定枚举 + JSONL 事件流（audit/events.jsonl：拦截/放行/晋升/导入）
- ✅ 门禁子串推断兜底记日志（§4 issue #3 对齐）
- ✅ MCP 新增 read_handoff / update_handoff 工具（14 个工具）

### 顺手修的既有 bug

- 🔧 search_semantic_facts：critical 无条件 +3 分导致**无关键词命中也返回**——显著性加权移到命中判据之后（MVP 测试暴露）

### 新增测试

- examples/test_mvp_schema.py：P1-P6（frontmatter/handoff/private 导出/指令扫描/lint 六项/旧格式兼容），退出码 0 = 全过
- examples/test_regression_v120.py：v1.2.0 回归不倒退（全过）

## 待做（MVP 后，P1/P2 后置）

- [ ] 按月文件 / agent 目录层 / raw jsonl 缓冲（§1 结构债）
- [ ] canon 200 条向量阈值开关（数据量未到）
- [ ] skills.md L3 指针表（V3：skill:名字 语法，1.0 定稿随行）
- [ ] superseded 状态机（决策考古）
- [ ] 语义提取（V1 Alice 案：缓上）
- [ ] 智能搜索（向量+关键词合一）
- [ ] 自动巩固定时触发
- [ ] 多智能体共享冲突处理
- [ ] cursor适配器
- [ ] 更多宿主支持

## 验收（§8 全单，验收官跑）

```bash
python -m agent_diary.lint <diary_base_dir>
# 退出码 0 = 六项全过
```

六项：① 字段完备 ② id 唯一排序 ③ canon 纯净 ④ private 不出门 ⑤ 状态位不互噬 ⑥ 门禁双路
