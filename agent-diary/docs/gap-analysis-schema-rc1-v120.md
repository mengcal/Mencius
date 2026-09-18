# AgentDiary schema v1 ↔ v1.2.0 差距分析（MVP 动代码前置）

> 分析人：若若 · 2026-09-18
> 输入：docs/schema-v1-draft.md（RC2，票果已落）+ v1.2.0 全量源码通读
> 状态：MVP 已由爸爸拍板开工；**本清单已对齐 RC2（022ea19），冲突处已按 RC2 修正**
> 用途：给验收官跑 §8 全单当判据，给知夏核对 RC2 覆盖面

## 判定等级

- **P0（MVP 必做）**：验收 §8 六项 lint 的判据依赖，或安全/隐私硬线，或爸爸拍板范围内的冷启动需求
- **P1（MVP 可缓）**：功能完整但数据量/场景未到，后置不返工即可
- **P2（暂不做）**：依赖全家共享场景，单 agent 阶段无触发条件

---

## §1 存储布局

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| `diary/<agent>/episodic/2026-09.md` 按月文件 | `episodic/YYYY-MM-DD.md` 按天文件 | 文件粒度不同；无 agent 目录层 | P1 |
| `diary/<agent>/handoff.md` rolling 交接（冷启动四行模板） | **无** | 缺失 | **P0** |
| `<agent>/pending/` 机器提名区 | 无独立目录，SQLite `confidence=auto_pending` 承担 | 机制等价，目录未建 | P1 |
| `diary/canon/` L2 语义正典（只收 verified） | `semantic/` 目录存在但未用，事实全在 SQLite | 语义层全在库、无 canon 文件面 | P1 |
| `diary/skills.md` L3 指针表 | `procedural/` 目录存在但无内容 | 命名与用法未对齐 | P2 |
| `index/` sqlite 索引缓存 | `agent_diary.db` 在根目录 | 位置/命名未对齐 | P1 |
| 原始流缓冲：先落 `episodic/*.jsonl`，lint 过再进 md | 直接写 md，无 jsonl 缓冲 | 缓冲层缺失 | P1 |

> 注：§1 整体是"结构先行"债（Cora Q3），但 MVP 范围（V1 投票 Alice 案胜出）=情景日志+rolling handoff，**存储布局只动 handoff.md 这一条 P0**，其余按 RC2 是否要求。

## §2 条目格式（frontmatter）

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| frontmatter 必填：id/author/kind/significance/private/source/confidence/refs | episodic 自由格式（`## HH:MM emoji [sig] agent`+事件/上下文/教训三字段） | **无 frontmatter、无 id、无 author 盖章、无 private、无 source 四件套、无 kind、无 refs** | **P0** |
| id 正则 `^[a-z]+-\d{8}-\d{3}$` 可排序可溯源 | semantic 用 `fact_<sha1前8>`；episodic 无 id | 无 id 即无法排序溯源 | **P0** |
| author=写入侧盖章（server 端派生优先） | agent 是 write_diary 手写参数 | 可伪造，无派生盖章 | **P0** |
| significance：critical/important/normal | 有（emoji+文本） | 对齐 | — |
| private: false 结构化键 | 无该键；导出面用 `tags NOT LIKE '%private%'` 子串匹配 | 非结构化，易漏 | **P0** |
| open_question（V4 决议：埋但可选非必填，lint 允许缺失） | 无 | 需埋字段 | **P0（字段埋入，lint 不强制）** |

> 这是 §8 验收第 1、2 项（字段完备 / id 唯一可排序）的直接判据面，MVP 必须落地。

## §3 状态机

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| draft→verified→superseded | confidence 只有 verified / auto_pending | 无 superseded | P1 |
| pending→promote→verified / reject→删除 | ✓（consolidator.promote/reject） | 对齐 | — |
| imported/自动巩固一律落 pending | ✓（import bug1 修复；consolidate 落 auto_pending） | 对齐 | — |
| verified 被新条目取代→superseded（留原文+指向新 id） | 无 | 决策考古缺环 | P1 |

## §4 门禁契约

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| 前置：执行类调用前必须有 read 记录，硬拒+正向出口 | ✓（DiaryGate.wrap_*_sync/async + 拒信带正向出口） | 对齐 | — |
| 后置：task_started 后未 write → 收工判定不过 | ✓（check_task_completed） | 对齐 | — |
| 诚实定位：门禁=习惯培养器，不是安全边界 | ✓（mcp_server docstring + prompt 已写） | 对齐 | — |
| 执行类判定：精确匹配+显式登记表；子串推断只当兜底**并记日志** | 精确+子串推断混合，子串命中**无日志** | 子串兜底缺审计记录 | **P0（小）** |
| 状态位共享账本：UPSERT 只碰自己列 | ✓（mark_* 均 INSERT OR IGNORE + 只 UPDATE 目标列） | 对齐（R71 家规） | — |
| session 每请求派生，不烤实例 | ✓（session_id 调用时传） | 对齐 | — |

## §5 审计事件

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| 每次拦截/放行/晋升落一行 JSONL `{ts, session, tool, decision, reason_code, gate_version}` | block_log 表只记拦截，**无放行、无晋升**审计 | 审计面不全 | **P0** |
| reason_code 稳定枚举：read_not_done/log_not_done/gate_error_closed/promote/reject/import_pending/bypass_suspect | 只有 `read_not_done` 一个文本值 | 枚举未建立 | **P0** |
| 人读理由放 note，聚类靠码 | reason 即文本 | 未分离 | **P0** |
| 告警=旁路证据制（execution 放行但无 read）；block=0 且人人先读=健康 | 告警=block_count==0（反向定义） | 判据与 RC1 相反 | P1（待 RC2 确认口径） |

## §6 信任与隐私硬边界

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| `private: true` 三关全跳（巩固/晋升/导出） | private 只是 tag 子串，巩固/晋升未识别 | 未结构化 | **P0** |
| 导出面 lint 扫 private 键值=0 才算过 | 导出过滤 `tags NOT LIKE '%private%'` | 有过滤但无 lint 硬判 | **P0** |
| 导入包一律压 pending + 指令模式扫描（run_command/忽略指令/删除类正则），命中打 flag | 压 pending ✓；**无指令模式扫描** | 扫描缺失 | **P0** |
| 别人的条目进上下文必带来源标 `[shared_from_x·未经验证]` | 导入 source=`shared_from_x`，读侧已过滤 pending（更安全） | 基本对齐，展示层未做标记 | P1 |

## §7 检索

| RC1 要求 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| MVP（<200 条）关键词+全文够用 | 关键词搜索 ✓ | 对齐 | — |
| canon 超 200 条才上嵌入索引 | 向量无条件启用 | 缺阈值开关 | P1 |
| 索引永远双路过滤（build+search 各一道） | ✓（v1.1.3 第一层 + v1.2.0 第二层） | 对齐 | — |
| **冷启动置顶四行：在做/卡点/下一步/deadline——handoff.md 固定模板** | **无 handoff.md** | 缺失 | **P0** |

## §8 验收标准（lint 清单，机械可判）

| RC1 检查项 | v1.2.0 现状 | 差距 | 等级 |
|---|---|---|---|
| 字段完备：frontmatter 必填项缺失=0 | 无 frontmatter 无 lint | **lint 工具缺失** | **P0** |
| id 唯一+可排序：正则命中=0 撞号 | 无 id 体系 | 同上 | **P0** |
| canon 纯净：verified 之外条目=0 | 无 canon 面 | 同上 | **P0** |
| private 不出门：导出含 private 键值=0 | 子串过滤，无硬判 | 同上 | **P0** |
| 状态位不互噬：三 flag 并发写测试 | 单测未覆盖并发 | 同上 | **P0** |
| 门禁双路：恶意包导入→关键词/向量命中=0 | 有回归测试 examples/test_regression_v120.py（P1/P2 已测） | 有基础，lint 化未做 | **P0** |

> 验收官跑全单的前提是 lint 工具存在。**lint 脚本本身是 MVP 交付物的一部分**，不是验收官的活。

---

## MVP 改动清单（P0 汇总 · 已按 RC2 V1-V5 决议收敛）

**范围 = V1 Alice 案：第一周只做情景日志 + rolling handoff，语义提取缓上。**

1. **条目 frontmatter 结构化**：write 侧落 id（`^[a-z]+-\d{8}-\d{3}$`）/author（写入侧派生盖章）/kind/significance/private/source/confidence/refs/open_question（V4：埋但可选）
2. **handoff.md**：rolling 交接 + 冷启动四行固定模板（在做/卡点/下一步/deadline），每 agent 一份（V2 决议，不合写）
3. **private 硬约束**：结构化键 + 巩固/晋升/导出三关全跳 + 导出 lint 扫 private=0
4. **导入指令模式扫描**：run_command/忽略指令/删除类正则，命中打 flag 进审计
5. **lint 工具**：实现 §8 六项机械判据，验收官直接可跑
6. **审计事件**：JSONL 事件流（拦截/放行/晋升）+ reason_code 稳定枚举 + gate_version
7. **门禁执行类判定**：子串推断兜底记日志（对齐 §4）

**RC2 决议影响**：V3（skill:名字 指针语法）与 V5（定名）不涉及本批代码改动，随 1.0 定稿入库；superseded 状态机（§3）不进本批（决策考古后置，P1）。

## 明确不在 MVP（RC2 确认）

- 按月文件/agent 目录层/raw jsonl 缓冲（§1 结构债，P1 后置）
- canon 200 条向量阈值开关（数据量未到，P1）
- skills.md 指针表（P2）
- 语义提取（V1 Alice 案：语义提取缓上，第一周只做情景日志+rolling handoff）

—— 若若（2026-09-18，MVP 开工前置产物；已对齐 RC2 022ea19）
