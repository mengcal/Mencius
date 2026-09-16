# M 平台 · 代码 WIKI（家底账）

> 2026-09-15 全码盘点生成（general-purpose 八区逐文件过目 + 知夏抽验四条重疑点属实）。范围=D:\m\workspace 全仓+guard+pkg+前端。只读盘点，未改一码。
> **用法**：换会话后的第一读物；每次大改后由知夏派单增量更新本文件。行数为盘点当日值。

## 一、七条链速览（先读这个）

| 链 | 核心件 | 一句话 |
|---|---|---|
| **闸门链** | `mia_agent/confirm_gate_c1.py`(现役主门,1070行) → `confirm_gate.py`(档位/名单单源) → `guard_scan.py`(机器安全门,~149格最厚覆盖) → `approvals.py`(爸爸批准登记处,指纹绑定消费即焚) → 前端 `BatchApprovalInterrupt.tsx`+`ToolCallBox.tsx` | 一切工具调用过 C1 四档门（plan/strict/auto_edit/supreme）；high 机器拒、ask 弹卡给爸爸、D2 连败自动降档（TTL 24h） |
| **派单汇报链** | `tools.py`(dispatch_to_xiaoquan/dispatch_external) → `cow_graphs.py`(部门图工厂,SubGate 全拦) → `dept_watch.py`(完工/受阻轮询唤醒,15s扫描) → `office/routers/tasks.py`(TASKS账本+webhook) → `useTaskAnnouncer.ts`(前端播报) | 米娅只分派；部门 run 结束由 dept_watch 注入【部门自动汇报】唤醒主线程转呈；对外岗走 external.py pending/claim/callback 状态机 |
| **模型档位链** | `model_tier.py`(派活定档,一期只标不切) → `models.py`/`providers.py`(make_model 工厂) → `run_config.py`(每轮换主脑/联网开关) → `vision.py`(识图三级优先) | 模型/服务商/密钥一律配置化（08-29 铁律），设置页唯一真源 |
| **守卫审计链** | `guard/m_guard.py`(SYSTEM 进程,DPAPI,618行) → `internal_key.py`(进程身份钥匙) → `skills_lock.py`(技能哈希锁) → `auth.py`(原生 API 纵深) → `sandbox.py`↔`sandbox_runner.py`(执行面隔离对锁) | 密钥验证外置于米娅进程；三本账：token_audit / approvals_log / runner_audit |
| **账本** | `approvals.py` / `token_admin.py` / `tasks.py` / `usage.jsonl` / `flow_obs.jsonl` | 一切经手必落账，`core._rotate_log` 三代滚动 |
| **前端** | `deep-agents-ui/src/`（60 ts/tsx，Next.js） | 批准面=批量/单卡+双钮；设置面=壳+10 tabs+context；**全 FE 零测试=最大盲区** |
| **测试资产** | `workspace/tools/`（19 测试+6 辅助，≈498 格）+ `guard/test_m_guard.py`（109 法） | 零 pytest 全自跑脚本；verify_*=逐批验证件、test_*=常回归件；跑法=宿主 .venv 或容器内 MIA_SRC |

## 二、逐区清单

### 区1 mia_agent（18 py）
`confirm_gate_c1.py` 现役主门（SelfLockDenyGate 拒出口+HITL 批量卡+when 档位路由+after_model 动态反选+SubGate+D2 压力降档）｜`confirm_gate.py` 判定单源（本体退役为被引件）｜`guard_scan.py` 米娅版 Mimosa（GNU rm 全形态 high/词界锚定/连续 high≥2 冻结）｜`acceptance_kit.py`+`task_brief.py` 验收字面量引擎（核对不过米娅的手）｜`approvals.py`(根级) 批准登记处｜`dept_watch.py` 汇报环（register 挂门放行处,v2 扫描式,行为测 30 格——test_dept_watch.py，09-15 d2v03fix3⑦ 后看门狗哑火/扫描异常 print 出声可观测）｜`graph.py` 主图装配（middleware 序=[C1→Scribe→compaction→RunConfig→FlowObserver→PlanCheck]）｜`tools.py` 工具集（edit_memory/manage_departments/email/lark/dispatch/list_async_tasks）｜`model_tier.py` 定档｜`external_guard.py` SSRF 十面+HKDF 子钥｜`cow_graphs.py` 部门图工厂（**无测试**）｜`flow_observer.py` 层3 只记不拦｜`plan_check.py` 层2 验收注入｜`remember_rules.py` 批准并记住（**无测试**）｜`sandbox.py` 沙箱客户端（**无测试**,与 sandbox_runner 对锁）｜`store.py` PG 镜像｜`models.py`/`prompts.py` 配置与人设。

### 区2 workspace 根级（22 py）
`agent_multimodel.py` 兼容转发桩｜`settings_mgr.py` 设置唯一管理面（打码版+`.settings_secrets` 隔离）｜`scribe_hook.py` 书记员中间件（**仅源码文本断言,无行为测**）｜`auth.py` 原生 API 鉴权（豁免清单手工维护）｜`internal_key.py` 进程钥匙｜`hearth_graph.py`/`roundtable_graph.py`/`chat_kit.py` 围炉+圆桌（**无单测,围炉有手工触测**）｜`run_config.py` 每轮配置+usage 计量｜`search_tools.py` 五源聚合搜索｜`providers.py` 模型工厂（头部服务商注记陈旧）｜`rag_engine.py` pgvector 三信号加权｜`mail_service.py` ClawEmail 托管（与 mia_home/email_tool.py 名近物异）｜`sandbox_runner.py` 沙箱服务端（**无测试**）｜`skills_lock.py`/`checkpointer.py`/`store.py`(langgraph 用,与包内同名不同物)/`vision.py`/`office.py` 装配壳。

### 区3 office（FastAPI 管理面）
`app.py` 三名单 token 门｜`core.py` 公共层（常数时间比对/滑窗频控/账本滚动）｜9 routers：`tasks`(派活+webhook)/`gates`(vision+codebuddy 代理门)/`misc`(批准/撤销/reset/guard_unlock/**reset_thread 三锁齐清**/remember-rules/reflect)/`token_admin`(密钥体系)/`providers`(Settings API v1)/`rag`/`external`(对外岗)/`lark`(飞书桥)——**其中 6 个无 HTTP 级测试**。

### 区4 tools（≈498 格测试资产）
常回归件：c1 群（unit33/e2e6/hook6）+d2_pressure(95 实跑，09-16 现况)+guard_scan(67)+r61h(55)+dept_watch(30)+scribe(43)+remember_rules(24)+cow_graphs(23)+r46(6)+r43(23)+r2(17)+task_brief(19)+plan_check(6)+model_tier(20)+external_guard(12)；verify_ 群：r61b2(16)/r61c(8+24)/r61e(25+22)/r61h(20)；辅助：keyfile/replay_real_cmds/reconcile_double_claim/lark_diag/lark_first_contact(无 docstring)。

### 区5 guard ｜ 区6 pkg
`m_guard.py`(618行,ssh-agent/DPAPI 双参照)+`test_m_guard.py`(109 法/225 断言，头部"95 断言"陈旧文案已于 09-15 d2v03fix3 修正)+四 cmd 安装件+数据件只登名目；`pack.py` 围剿包（凭据扫描拒发+增量对账,**无测试**,须知停在 r25 时代）。

### 区7 前端（60 ts/tsx，零测试）
批准面 Batch/单卡+ToolCallBox；设置面 壳+10tabs+context+providerApi(Bearer 统一)+SetupWizard；`useTaskAnnouncer`=汇报播报；**/external、/lark、/vision、/usage 等 8 组端点无 FE 消费**（管理面走 curl/米娅工具）。

### 区8 mia_home（数据区）
notes 156 件（三本账+plan/meeting 档案）/langgraph 1153 落盘/memory/diary/tmp；**MIA-MOVE/=08-31 搬家归档（米娅自处理）**；散件 fibonacci.py=死件、4 空目录历史遗留。

## 三、已知盲区与待办（只列不修，2026-09-15 盘点时点）

1. **无测试带（09-15 dwfix 后更新）**：~~dept_watch、scribe_hook、remember_rules、cow_graphs~~ 已清零——四套常驻回归件 126 格上线，且开火首日逮住并修复 dept_watch 两段式唤醒死代码（请示后完工永不唤醒，dwfix-20260915，容器内 30/30）。仍欠：sandbox 对锁两侧、hearth/roundtable、settings_mgr（仅间接）、office 6/9 routers、pack.py、**前端全部**。
2. **assert_gate_order 已接线**（09-15 夜保险丝单）：graph.py 提 _middleware 具名变量、编译前调用，漏装=启动炸 fail-closed，活体 import 已验；**遗留**：函数语义是"存在性"非"顺序"，docstring 的"顺序/子层"空头承诺待下批清理（子层三处 cow_graphs 断言另单）。
3. **死件**：office_settings.html、office-old-backup.html、fibonacci.py、4 空目录；~~SelfLockDenyGate~~ 爸爸 09-15 夜裁**保留**（NOVA 送审稿档案=待部署配套件，绑 v0.3 桌面二期整体复活）。
4. **文案陈旧**：providers.py 服务商注记（08-24）、pack 须知（09-07）。（test_m_guard 头部"95 断言"→实数 225 已于 09-15 d2v03fix3 修正销账——Cora 第 0 号案例。）
5. **副本树漂移风险**：D:\m 下 backups/、github-release/、mencius-push/ 三棵同源树+多版本并存（本次未入账）。
6. **同名易混**：两个 store.py（根级=langgraph 自用/包内=PG 镜像）；approvals.py 本体在根级、office misc 只是 HTTP 壳。
7. **测试卫生**：test_guard_scan 每跑向真审批账写数据（应改道 temp）；test_d2_pressure 头部 docstring 目录未随 J-M 格更新。

## 四、维护契约
每次 D:\m 结构性改动（新文件/退役/接线/盲区变化）后，知夏派单增量更新本文件对应行；盘点全量重做每季度一次。**本文件随代码仓定期自动备份留档**。
