# AgentDiary v1.3.4

当前版本：v1.3.4（MVP，schema v1 RC2 对齐 + gate_hook v1.2 纳仓收讫）

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
| v1.3.0-mvp1 | schema v1 RC2 对齐 MVP（V1 Alice 案：情景日志+rolling handoff） |
| v1.3.1 | 知夏验收三条意见全落地：deny 带 session id + 告警不误报 + 回归测试缺依赖 skip + lint ⑦ refs 完整性 |
| v1.3.2 | refs-lint ⑦ 判据定稿（issue #8 评估落地：格式 error/断链 error/superseded warning）+ 修 append_episodic 返回 id（refs 引用链路）+ P7 验收测试 |
| v1.3.3 | lint ⑧ 版本一致（__version__==CHANGELOG 头，机器拦，知夏二犯复盘）+ 白名单盲区回执（仓库侧精确匹配无病灶） |
| **v1.3.4** | **gate_hook v1.2 纳仓收讫（知夏 09-26 b2d4b48：九例回归+路径参数化+GATE-OFF 急停）+ README 同步 hooks 说明** |

## v1.3.4（gate_hook 纳仓收讫，2026-09-26）

### 已完成

- ✅ gate_hook v1.2 纳仓（知夏 b2d4b48 已推）：`hooks/gate_hook.py` + `hooks/README.md` + `hooks/test_gate_hook.py`
  - 判定链：GATE-OFF 急停 → Bash 只读白名单（shlex 分词/复合按段/前导 env 跳过/sed 仅 -n 无 -i/git 安全子命令/`diary.py read` 活路）→ 已读放行 → 否则 deny+log_block
  - 路径参数化：`GATE_DIARY_ROOT`（默认 `~/.agent-diary/live`）、`GATE_DIARY_PKG`（默认本仓根推导），无个人机器路径
  - 附带修复：GATE_DIARY_PKG 默认值原推导错（包目录）→ 改为仓根，`from agent_diary.store` 可导入
- ✅ 九例回归对照通过（`python hooks/test_gate_hook.py`，14 check 全绿）
- ✅ README 补「门禁钩子 gate_hook」段落（协议/判定/安装/急停/回归入口），对齐纳仓

### 回归

- 全量：验收测试（§8 八项+MVP）、v1.2.0 回归、demo、check_version——全过

## v1.3.3（知夏 09-22 两单 bug 回执，2026-09-22）

### 已完成

- ✅ lint 新增 ⑧ 版本一致：`agent_diary/__init__.py __version__ == CHANGELOG.md 头版本号`（机械可判）
  - 背景：版本串滞后**二犯**（v1.1.0 串 v1.2.0、v1.3.0-mvp1 串 v1.3.2）——不能靠自觉，必须机器拦
  - 与 scripts/check_version.py（e447138 已加）同判据；lint 收口进验收单，验收官跑全单即抓
  - §8 七项→八项
- ✅ 白名单盲区回执（bug 1）：仓库侧 memory_gate.py 的 `is_safe_tool` 是**精确集合匹配**（`tool_name in SAFE_LIST`），无 startswith 引号/复合命令盲区；知夏宿主侧 gate_hook v1.1 已自修（shlex 分词+段头 basename+sed 有 -n 无 -i 收口），本仓库无对应代码需改
- ✅ 测试文案同步 §8 八项（test_mvp_schema P5/README/lint 头注释）

### 新增测试

- examples/test_mvp_schema.py：P1-P7（P5 lint 八项自动覆盖 ⑧），退出码 0 = 全过
- scripts/check_version.py：机械自检 __version__ == CHANGELOG 头（e447138 引入，本版双处同步验证）

## v1.3.2（知夏 issue #8 提案评估定稿，2026-09-19）

### 已完成

- ✅ lint ⑦ 完整对齐 issue #8 判据（v1.3.1 只查孤儿引用，本次按知夏口径定稿）：
  - 存在性：ref 指向的 id 必须在全库 id 全集（episodic + canon + pending 都算，pending 可引用）
  - 格式：严格匹配 `^[a-z]+-\d{8}-\d{3}$`（复用 §8 ② 同一正则，不另立），不匹配 = error
  - 前缀：全小写；不做 agent 前缀白名单——悬空就是悬空，谁的都算断
  - superseded 被引用 = warning（历史考古合法），不算 error
  - 输出：`refs 断链=N（error）+ 指向 superseded=M（warning）`，N=0 才算过
- ✅ **修 append_episodic 返回条目 id**（P7 暴露的隐藏 bug）：此前返回文件路径，调用方拿不到 id 就写不出正确 refs——V2 共享靠 refs 链接，这是断链源头；mcp_server/tools 改用 get_episodic_path 补路径（source/展示用）
- ✅ 验收测试补 P7（issue #8 要求）：断链 error / 格式 error / 存在即过 / superseded warning 四项全过
- ✅ superseded 状态机未实现（待做），lint ⑦ 按 confidence='superseded' 预留判定

### 新增测试

- examples/test_mvp_schema.py：P1-P7（P7=refs 链接完整性四场景），退出码 0 = 全过
- examples/test_regression_v120.py：v1.2.0 回归不倒退（缺依赖自动 SKIP 向量部分）

## v1.3.1（知夏 13:35 验收意见，2026-09-18）

### 已完成

- ✅ deny 拒信带当前 session id（排查"为什么被拦"不用自己猜会话号，dogfood 反馈①）
- ✅ 仪表盘"拦截=0"告警区分门禁模式/CLI 直写模式（dogfood 反馈②）：
  - 门禁已接入（今天有 pass/block 审计事件）但拦截=0 → 告警"拦截可能没生效"
  - 无门禁事件（纯库/CLI 直写）→ 提示"门禁未接入，拦截=0 属正常直写"，不再误报
- ✅ 回归测试缺 sentence-transformers 时向量部分 SKIP+如实报（学 lint，不崩不搭 venv，验收意见①）
- ✅ lint 新增 ⑦ refs 完整性（知夏意见③，V2 共享靠 refs 链接）：refs 引用的 id 不存在=孤儿引用，lint 可见；§8 六项→七项

### 新增测试

- examples/test_mvp_schema.py：P1-P6（frontmatter/handoff/private 导出/指令扫描/lint 七项/旧格式兼容），退出码 0 = 全过
- examples/test_regression_v120.py：v1.2.0 回归不倒退（缺依赖自动 SKIP 向量部分）
- 专项验证（v1.3.1）：deny 带 session id、CLI 直写不误报、门禁模式正常告警——全过

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
# 退出码 0 = 七项全过
```

七项：① 字段完备 ② id 唯一排序 ③ canon 纯净 ④ private 不出门 ⑤ 状态位不互噬 ⑥ 门禁双路 ⑦ refs 完整性
