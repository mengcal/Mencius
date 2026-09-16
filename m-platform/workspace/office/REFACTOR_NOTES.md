# REFACTOR_NOTES —— office.py（1901 行）拆分对照表

来源：`D:\m\workspace\office.py`（1902 行，含尾空行；正文至 :1901）。
输出：`D:\sandbox-workspace\scratch\refactor\office\`（= 新 `office/` 包，整体放回 workplatform 根即可用）。
**未改动 D:\m 下任何文件**（仅读）。所有新文件开头注释均标明来源行号段。

---

## 1. 拆分对照总表（原行号 → 新文件）

| 原行号 | 内容 | 新位置 |
|---|---|---|
| :1-13 | 模块文档 | `app.py` 文档头（保留用法说明） |
| :14-21 | 顶层 import（asyncio/os/urllib.error/threading/time/Path） | 按"最小需要"分散：os/time→`core.py`；threading→`tasks.py`/`token_admin.py`；asyncio→`rag.py`/`gates.py`/`tasks.py`；urllib.error→`token_admin.py`；Path→`core.py`/`gates.py` |
| :22 | `print("[office] STEP0 start")` | `app.py` |
| :24-28 | dotenv + BASE + STEP0.5 | `core.py`（BASE 上跳一级，见 §3-A） |
| :30-33 | agent_multimodel 加载 | `app.py` |
| :35-37 | `from vision import analyze_image` | `routers/gates.py` 顶部（STEP3 打印留在 `app.py`） |
| :39-40 | `_lock` | `routers/tasks.py`（misc 的 /stats 横向复用） |
| :43-48 | FastAPI import + `app = FastAPI(...)` | `app.py` 的 `create_app()`；router 改用 `APIRouter()` |
| :51-70 | `_secrets_dir` / `_ck` | `core.py` |
| :73-76 | `VisionReq` | `routers/gates.py` |
| :79-93 | /runs 退役注释 + TASKS/_TSEQ/_webhook_lock/_TASKS_FILE | `routers/tasks.py` |
| :96-105 | `_load_tasks_persisted` | `routers/tasks.py` |
| :108-123 | `_save_tasks` | `routers/tasks.py` |
| :126-135 | TASKS 恢复 + `_TSEQ` 推进（模块级启动副作用） | `routers/tasks.py` |
| :138-149 | `_sdk_client` | `routers/tasks.py` |
| :152-165 | POST /files/save | `routers/tasks.py` |
| :168-175 | RAG 存储层说明 + `_RAG_VEC`/`_RAG_DIM` | `routers/rag.py` |
| :178-198 | `_rag_pg` | `routers/rag.py` |
| :201-226 | `_rag_migrate_json` | `routers/rag.py` |
| :229-236 | `_rag_load` | `routers/rag.py` |
| :239-241 | `import skills_lock` + `_SKILLS_DIR` | `routers/misc.py`（_SKILLS_DIR 改用 BASE，见 §3-B） |
| :244-267 | GET /skills/list、POST /skills/rehash | `routers/misc.py` |
| :270-276 | RAG 频控窗常量（_RAG_HITS_* / _RAG_RATE_*） | `routers/rag.py` |
| :277 | `_DISPATCH_HITS` | `routers/tasks.py`（归 dispatch 所用） |
| :280-285 | `_rag_cos` | `routers/rag.py` |
| :288-323 | POST /rag/ingest | `routers/rag.py` |
| :326-376 | POST /rag/query（第三扇代理门） | `routers/rag.py` |
| :379-393 | GET /rag/list | `routers/rag.py` |
| :396-415 | GET /rag/stats | `routers/rag.py` |
| :418-460 | `_RAG_REBUILDING` + POST /rag/rebuild | `routers/rag.py` |
| :463-469 | `_WHBK` + `_webhook_url` | `routers/tasks.py` |
| :472-526 | POST /tasks/dispatch | `routers/tasks.py` |
| :529-613 | POST /tasks/webhook | `routers/tasks.py` |
| :616-640 | GET /tasks/list | `routers/tasks.py` |
| :643-669 | GET /usage/today | `routers/misc.py` |
| :672-706 | GET /context/threads | `routers/misc.py` |
| :709-724 | GET /stats | `routers/misc.py` |
| :727-740 | /vision 常量（双窗 + `_VISION_USAGE_LOG`） | `routers/gates.py` |
| :743-752 | `_rate_ok`（通用滑动窗口） | `core.py` |
| :755-772 | `_vision_usage_log` | `routers/gates.py` |
| :775-823 | POST /vision（第一扇代理门） | `routers/gates.py` |
| :826-851 | CodeBuddy 常量 + `_CB_USAGE_LOG` 选路块 | `routers/gates.py` |
| :854-862 | 注释块 + `_VISION_MAX_BODY` | `routers/gates.py` |
| :865-872 | `_send_413` | `routers/gates.py` |
| :875-926 | `_BodyCap` 类 | `routers/gates.py` |
| :929 | `app.add_middleware(_BodyCap)` | `app.py` 的 `create_app()`（注册动作；类在 gates） |
| :931-948 | `_ROTATE_BYTES` + `_rotate_log` | `core.py` |
| :953-962 | `_cb_allowed_models` | `routers/gates.py` |
| :965-974 | `_cb_rate_ok` | `routers/gates.py` |
| :977-991 | `_cb_usage_log` | `routers/gates.py` |
| :994-1103 | POST /codebuddy/chat/completions（第二扇代理门） | `routers/gates.py` |
| :1106-1108 | GET /health | `routers/misc.py` |
| :1111-1129 | POST /approvals | `routers/misc.py` |
| :1132-1142 | DELETE /approvals | `routers/misc.py` |
| :1145-1152 | `import json as _json`、HTMLResponse/FileResponse、`_RawResp`、CORS、裸 Response | `_json`→`rag.py`+`misc.py` 顶部（见 §3-C）；HTMLResponse/FileResponse→`misc.py`；`_RawResp`/`_JSONResp`→`core.py`；CORSMiddleware→`app.py`；裸 `from fastapi import Response`→`core.py`（原样保留） |
| :1157-1161 | `import secrets as _secrets`、`_JSONResp`、settings_mgr token 导入 | `_secrets`/settings_mgr 导入→`token_admin.py`；`_JSONResp`→`core.py` |
| :1163-1180 | `_TOKEN_GUARDED` / `_GET_GUARDED` / `_GET_EXEMPT` | `app.py`（按拆分规则） |
| :1183-1188 | bootstrap 说明注释 + `_TOKEN_BOOTSTRAP` | `routers/token_admin.py` |
| :1191-1196 | `_bootstrap_read` | `routers/token_admin.py` |
| :1199 | `_BOOT_LOCK` | `routers/token_admin.py` |
| :1202-1217 | `_token_audit` | `core.py`（misc 的 /approvals 也要用，见 §3-D） |
| :1220-1233 | `_BOOT_BUCKETS` + `_boot_rate_ok` | `routers/token_admin.py` |
| :1236-1263 | `_bootstrap_ensure` | `routers/token_admin.py` |
| :1266-1271 | `_bootstrap_drop` | `routers/token_admin.py` |
| :1274-1276 | 启动即备好激活码（模块级副作用） | `routers/token_admin.py` |
| :1279-1281 | `_guard_url` | `routers/token_admin.py` |
| :1284-1297 | `_presented_token` | `core.py`（app 守卫也要用，见 §3-D） |
| :1300-1316 | `api_token_guard` 中间件 | `app.py`（在 create_app 内挂载，顺序不变） |
| :1318-1324 | CORSMiddleware 注册 | `app.py` 的 `create_app()` |
| :1328-1330 | GET /settings/token/status | `routers/token_admin.py` |
| :1333-1420 | POST /settings/token（首设/轮换，guard 双模式） | `routers/token_admin.py` |
| :1423-1461 | POST /auth/set_password | `routers/token_admin.py` |
| :1464-1501 | POST /auth/login | `routers/token_admin.py` |
| :1504-1550 | DELETE /settings/token | `routers/token_admin.py` |
| :1552-1574 | /config（旧指引）、/settings_page、/office、/ | `routers/misc.py` |
| :1577-1613 | POST /threads/title | `routers/tasks.py` |
| :1616-1661 | settings_mgr/httpx 导入 + GET /settings + POST /settings/{section} | `routers/providers.py` |
| :1663-1675 | /providers/fetch_models 已删除注释 + GET /providers | `routers/providers.py` |
| :1678-1697 | `_assert_public_fetch_target`（SSRF 闸门） | `routers/providers.py` |
| :1700-1711 | `_fetch_models_async` | `routers/providers.py` |
| :1714-1728 | `_save_external_provider` | `routers/providers.py` |
| :1731-1896 | /providers/add·rename·refresh·toggle·delete·update + GET /models/all | `routers/providers.py` |
| :1899-1901 | `if __name__ == "__main__"` uvicorn 入口 | `app.py`（装配壳 office.py 亦有等价入口） |

路由核对：原文件 40 个路由（按 @app 装饰器计），新包 40 个（tasks 5 + misc 13 + rag 5 + gates 2 + token_admin 5 + providers 10），无遗漏、无重复注册。

---

## 2. 装配壳（替换原 office.py 的内容）

```python
"""米娅「工作平台·小全车间」异步派活服务 —— 装配壳（拆分后）
实现位于 office/ 包：office/core.py、office/app.py、office/routers/*（见 REFACTOR_NOTES.md 对照表）。
用法不变：
    cd /home/user/workplatform
    nohup /home/user/wp-venv/bin/python -u office.py > wp_run.log 2>&1 &
"""
from office.app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=2024, log_level="info")
```

---

## 3. 必要的适配决策（与逐字搬运的唯一差异，均已在文件头注释标注）

- **A. BASE 上跳一级**：原 `BASE = Path(__file__).parent`（office.py 在 workplatform 根）。包化后 `core.py` 位于 `office/` 内，改为 `Path(__file__).resolve().parent.parent`，语义仍 = workplatform 根。所有依赖 BASE 的路径（mia_home、settings.json、office.html、_TASKS_FILE、_RAG_VEC、_CB_USAGE_LOG 回落路径）随之保持原语义。`_secrets_dir` 的回落 `BASE.parent / "secrets"` 不变。
- **B. `_SKILLS_DIR` 改用 BASE**：原 `Path(__file__).parent / "mia_home" / "skills"` 同理改为 `BASE / "mia_home" / "skills"`。
- **C. `import json as _json` 提前**：原 :1148 延迟到文件后部才定义，而 :210/:233/:322 的 RAG 函数先于它定义（运行期才取名，侥幸可用）。拆分后 `rag.py`、`misc.py` 各自在顶部显式导入，消除"先定义后导入"的隐式依赖。
- **D. 两个共用函数下沉 `core.py`**：
  - `_token_audit`——除 token_admin 外，misc 的 /approvals（原 :1125）也调用；
  - `_presented_token`——除 token_admin 外，app.py 的 api_token_guard（原 :1314）也调用。
  两者均为纯函数且只依赖 core 内的 `_secrets_dir`/`_rotate_log`，放公共层可避免 router 互相依赖或反向依赖 app。
- **E. `_JSONResp` / `_RawResp` 导入别名归 `core.py`**：原 :1150/:1160 是模块级别名，被 rag/gates/tasks/token_admin/app 五方使用；统一从 core 导入。
- **F. `/models/all` 归属裁定**：拆分方案中 providers 清单与 misc 清单重复列了 /models/all。按数据归属定到 `routers/providers.py`（读 external.providers[].models_cache），misc 不注册，避免同路径双注册（FastAPI 先注册者赢，第二个成了死路由）。
- **G. 路由注册顺序约束**：`create_app()` 中 `token_admin.router` 必须先于 `providers.router` include——POST /settings/token（实名）必须抢在 POST /settings/{section}（路径参数）之前，否则首设/轮换被 {section} 吞掉（原源码序 :1333 早于 :1633，等价保持）。
- **H. 中间件叠放顺序保持**：create_app 内按原顺序 add：`_BodyCap`(:929) → `api_token_guard`(:1300) → `CORSMiddleware`(:1318)。FastAPI/Starlette 后 add 者在外层，最终 CORS 最外、守卫次之、体积闸最内、路由最后——与原版运行时行为一致。
- **I. 模块级 `app` → `APIRouter` + `create_app()`**：router 禁止反向 import app，故各 router 改用 `APIRouter()`，由 app.py 统一 include；`app = create_app()` 在 app.py 模块级执行，装配壳 `from office.app import app` 语义不变。
- **J. STEP 打印顺序微调**：`STEP3 vision loaded` 的打印在 `routers.gates` 导入之后（vision 随 gates 导入），其余 STEP0/0.5/1/2/6 位置不变。
- **K. 依赖导入收紧**：原 :44 `from fastapi import FastAPI, Body, Request` 中 Body/Request 在 app 层不再需要（router 各自导入）；原 :1161 的 `get_api_token` 在 token_admin 顶层未直接使用（`_sdk_client` 的局部导入留在 tasks.py）——该行按原样保留以保真，未删项。

---

## 4. 循环依赖核查

依赖方向（单向，无环）：

```
core.py（叶子：os/time/dotenv/fastapi Response/starlette JSONResponse）
  ↑
routers/rag.py、gates.py、tasks.py、token_admin.py、providers.py、misc.py
  ↑                        （misc → tasks 横向引用 TASKS/_lock，允许）
app.py（core + 全部 routers + agent_multimodel/vision/settings_mgr）
  ↑
office.py 装配壳（from office.app import app）
```

workplatform 本地模块（agent_multimodel、vision、settings_mgr、skills_lock、approvals、providers、rag_engine、internal_key、langgraph_sdk）均为包外平级模块，workplatform 在 sys.path 时照常解析，不需要改动。

---

## 5. 文件清单（本次输出）

```
D:\sandbox-workspace\scratch\refactor\office\
├── __init__.py              包说明 + 模块地图
├── core.py                  纯函数/常量层（~135 行）
├── app.py                   装配层（create_app/守卫/uvicorn，~150 行）
├── routers\
│   ├── __init__.py
│   ├── providers.py         /settings*、/providers*、/models/all、SSRF 闸门（~300 行）
│   ├── rag.py               RAG 存储层 + 五个 /rag/*（~310 行）
│   ├── gates.py             _BodyCap 类 + /vision + /codebuddy（~430 行）
│   ├── tasks.py             TASKS 账本 + /tasks/* + /files/save + /threads/title（~330 行）
│   ├── token_admin.py       激活码 + /settings/token + /auth/*（~330 行）
│   └── misc.py              /skills、/usage、/context、/stats、/health、/approvals、旧路径（~230 行）
└── REFACTOR_NOTES.md        本文件
```

行数与审定方案（core ~120 / providers ~300 / rag ~300 / gates ~380 / tasks ~350 / token_admin ~300 / misc ~250 / app ~100）基本吻合；gates 因把三扇门的同型防护对照注释并入而略超，属注释量差异，代码本体逐行对应原文。
