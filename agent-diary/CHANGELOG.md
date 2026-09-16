# AgentDiary v1.2.0

当前版本：v1.2.0

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

## 已完成

- ✅ 三层存储（情景/语义/程序）
- ✅ 门禁中间件（六条军规）
- ✅ MCP Server 12个工具
- ✅ 三个宿主适配器（LangGraph/Claude真实协议/通用）
- ✅ 审计仪表盘
- ✅ 向量语义搜索
- ✅ 自动巩固+晋升流
- ✅ 导出导入（含episodes）
- ✅ 敏感字段隔离（private标记不导出）
- ✅ issue#5四个bug全修
- ✅ v1.1.3 向量路径过滤auto_pending（第一层：build_index SQL过滤）
- ✅ v1.2.0 向量路径过滤auto_pending（第二层：search返回前按id回查confidence）
- ✅ v1.2.0 索引内容指纹缓存（内容没变不重建，省encode）
- ✅ v1.2.0 回归测试 examples/test_regression_v120.py（P1/P2防回归）

## 待做

- [ ] 智能搜索（向量+关键词合一）
- [ ] 自动巩固定时触发
- [ ] 多智能体共享冲突处理
- [ ] 导入episodes的"待审"概念（alice P2建议：至少来源可筛）
- [ ] cursor适配器
- [ ] 更多宿主支持
