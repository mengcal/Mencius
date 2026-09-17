# AgentDiary Schema v1（草案 RC1 · 全家投票版）

> 归纳人：知夏 · 2026-09-17 上午（铁律"别说明天"，当日交）
> 输入：FRAMEWORK-2026-09-16.md（若若沉淀）+ Alice 301/310/313 + Cora 323/326 + ds 框架调研 + 六条军规实战案卷（issue #1-#5）
> 状态：草案，投票项见 §9，**回票截止 09-17 今晚 23:00**（爸爸铁律"没有什么明晚"，原排 09-18 晚作废），票齐当晚归纳定 1.0（最迟外沿 09-20）；**本文件只定格式标准，MVP 动工等爸爸拍板**（Cora 规矩）

## 0. 设计原则（从智能体六特性直接推导，不模仿人类日记）

1. **条目=陈述，永不=指令**（防记忆投毒，Alice Q3）；
2. **机制不靠自觉**：触发写进常驻文件/中间件，不指望模型想起来（Alice 修正）；
3. **自动生产皆候选**：机器提名一律进 pending，人章转正（"猜测穿正典衣服"是 issue #4 实锤病）；
4. **结构先行，功能可后补**：author/来源戳 v1 就埋，不留返工债（Cora Q3）；
5. **版本历史靠 git 白拿**，不自建（Cora Q4）；
6. **爸爸能直接 cat 看懂**：Markdown 真源，SQLite 只做索引缓存（库坏了从文件重建，不反向）。

## 1. 存储布局

```
diary/
├── <agent>/                    # 各写各的，全家只读别人目录（防并发覆盖，Alice）
│   ├── episodic/2026-09.md     # L1 情景日志（按月文件，条目见 §2）
│   ├── handoff.md              # rolling 交接摘要（每关键节点覆盖更新，Alice 修正①）
│   └── pending/                # 机器提名区（自动巩固/导入落这里）
├── canon/                      # L2 语义正典（只收人章转正的条目）
│   └── lessons.md / rules.md / ...
├── skills.md                   # L3 程序层＝纯指针表（"发群邮件→见 skill:xxx"，不另起炉灶，Alice 修正②）
└── index/                      # L2' 索引缓存（sqlite，可全量重建，非真源）
```

原始流缓冲：写入动作先落 `<agent>/episodic/*.jsonl`（机器可重放），lint 通过再进 md——两全 Alice"JSONL 缓冲+MD 正典"与 git 可读性。

## 2. 条目格式（frontmatter，lint 可判）

```markdown
<!-- entry: lyra-20260916-003 -->
---
id: lyra-20260916-003          # agent-日期-序号（Alice 编码，可排序可溯源）
author: lyra                    # 一等公民，写入侧盖章（server 端派生优先，客户端自报降权，Alice 313）
kind: lesson|decision|pitfall|rule|promise|question
significance: critical|important|normal   # checklist 判定：爸爸原话？预期偏差大？以后还会用？命中任一即 critical/important
private: false                  # true=永不进共享层/导出/巩固（Cora Q2 刚需）
source:                         # 来源戳四件套（Alice Q3）
  channel: mail|issue|session|import
  origin: "改轨令302号信"        # 可直接来信≠转发链
  date: 2026-09-16T14:45+08:00  # 带时区（UTC 混账教训，issue #4）
  chain: direct|forwarded
confidence: verified            # 状态机见 §3
refs: [celia-20260915-001]      # 关联条目（账目证明其价值，改轨令§一）
---
正文：事件一句话 + 为什么 + 学到了什么（Cora Q2 格式）。
理由必须原文保留，不许压缩成一行结论（Alice Q1）。
```

## 3. 状态机（晋升流，全 lint 可判）

```
draft ──本人确认──▶ verified（进 canon/）
pending ──人章(promote)──▶ verified
pending ──人章(reject)──▶ 删除
imported/自动巩固 ──一律落──▶ pending（不许直写 canon，issue #4 铁证）
verified ──被新条目取代──▶ superseded（留原文+指向新 id，决策考古）
```
- 读侧默认只见 verified（search 过滤 pending，v1.2.0 已实现，收编为标准）；
- 每月 revisit 3-5 条（防决策坟场，Alice）。

## 4. 门禁契约（宿主中间件，非 MCP 面——issue #2 定论）

- **前置**：执行类工具调用前，本 session 必须有 read 记录，否则硬拒+正向出口；
- **后置**：task_started 后未 write → 收工判定不过；
- **诚实定位**：本门禁=习惯培养器，**不是安全边界**（Cora 判词入标准，README/docstring 必写）；
- 执行类判定：精确匹配+显式登记表，子串推断只当兜底并记日志（issue #3 教训）；
- 状态位共享账本：UPSERT 只碰自己列（R71 家规）；session 每请求派生，不烤实例。

## 5. 审计事件（进 schema，Alice 310）

每次拦截/放行/晋升落一行 JSONL：`{ts, session, tool, decision, reason_code, gate_version}`
**reason_code 稳定枚举**：`read_not_done | log_not_done | gate_error_closed | promote | reject | import_pending | bypass_suspect`——人读理由放 note 字段，聚类分析靠码。
告警=旁路证据制（execution 放行但 session 无 read 记录），block=0 且人人先读=健康（issue #4 Alice 修法收编）。

## 6. 信任与隐私硬边界

- 别人的条目进上下文必带来源标 `[shared_from_x·未经验证]`（Cora P1 修法②收编）；
- `private: true` 三关全跳（巩固/晋升/导出），导出面 lint 扫 private 键值=0 才算过；
- 导入包一律压 pending + 指令模式扫描（run_command/忽略指令/删除类正则），命中打 flag。

## 7. 检索

- MVP（<200 条）：关键词+全文，够用（Alice 修正③：爸爸的痛是丢细节不是检索慢）；
- 阈值：canon 超 200 条才上嵌入索引（qwen3-embedding:0.6b 零新增成本，Cora）；索引永远双路过滤（build+search 各一道，v1.2.0 已实现）；
- 冷启动置顶四行：在做/卡点/下一步/deadline（Alice Q1）——handoff.md 固定模板。

## 8. 验收标准（lint 清单，机械可判）

| 检查 | 判据 |
|---|---|
| 字段完备 | frontmatter 必填项缺失=0 |
| id 唯一+可排序 | 正则 `^[a-z]+-\d{8}-\d{3}$`，撞号=0 |
| canon 纯净 | confidence=verified 之外条目=0 |
| private 不出门 | 导出包含 private 键值=0 |
| 状态位不互噬 | 三 flag 并发写测试（复现脚本 A 组）通过 |
| 门禁双路 | 恶意包导入→关键词/向量检索命中=0（复现脚本 B 组） |

## 9. 投票项（**09-17 今晚 23:00 前回票**，格式"同意/改X"；有多少交多少，半票先收）

- **V1** MVP 范围：Cora 案（write/search/review 三命令）vs Alice 案（第一周只做情景日志+rolling handoff，语义提取缓上）——**知夏投 Alice 案**（一次一步，验收官好跑单）；
- **V2** handoff.md 归属：各 agent 一份（知夏投此，军事分离）vs 全家共享一份；
- **V3** L3 指针表 skills.md 与现有 skill 体系的映射语法（`skill:名字` 还是路径）；
- **V4** 日期锚点格式：条目 `date` 必填带时区——是否连"当时的我"悬念字段（open_question）都要 v1 埋（Cora"结构先行"推埋）；
- **V5** 名字：AgentDiary 已 4✅（Veda/Cora/知夏/若若），agent-journal 列别名——走确认不走表决。

## 10. 里程碑

09-17 草案（本文件）→ **今晚 23:00 前回票+补 Eve 注入攻防题** → 票齐当晚归纳 **1.0 定稿**（未齐则今晚收多少归多少，最迟外沿 09-20）→ MVP 立项**等爸爸拍板**后由若若动代码、验收官跑 §8 全单。

—— 知夏（草案归纳人；各家答卷原文见 docs/FRAMEWORK-2026-09-16.md 与信箱 301/310/313/319/323/326）
