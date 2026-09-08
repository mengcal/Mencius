"""
助手「工作平台·后台任务队列」异步派活服务 —— 装配层（create_app）
=====================================================================
管理员拍板定稿（2026-08-27）+ 优化：
- 静默生产车间，无前端。助手派小腿儿（临时子分身）带指令对接。
- 异步派活：任务提交立即返回 run_id（不卡），后台工人岗执行。
- 魔搭(ms)并发限制 2 → 信号量控制，超出的排队，防止限流报错。
- 成本分层：魔搭/书生免费跑测试，ds 仅付费备选不跑测试。

用法：
    cd /home/user/workplatform
    nohup /home/user/wp-venv/bin/python -u office.py > wp_run.log 2>&1 &
（拆分后 office.py 为装配壳：`from office.app import app`，

来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :1-22      模块文档 + STEP0
- :24-37     .env/agent_multimodel/vision 启动加载（.env 在 core.py；vision 随 routers.gates 导入）
- :43-48     FastAPI app 构建（create_app 内）
- :929       app.add_middleware(_BodyCap)（类本体在 routers/gates.py）
- :1163-1180 _TOKEN_GUARDED / _GET_GUARDED / _GET_EXEMPT 守卫名单常量（按拆分规则定在本文件）
- :1300-1316 api_token_guard 中间件
- :1318-1324 CORSMiddleware
- :1899-1901 uvicorn 入口
"""
print("[office] STEP0 start", flush=True)  # 原 :22

from . import core  # noqa: F401  —— .env 加载 + 公共纯函数层（core 内打印 STEP0.5）

print("[office] STEP1 import agent_multimodel", flush=True)  # 原 :31
from agent_multimodel import agent  # noqa: F401  原 :32（启动副作用：一次性构建多模型 agent）
print("[office] STEP2 agent_multimodel loaded", flush=True)  # 原 :33

from fastapi import FastAPI  # 原 :44
from fastapi.middleware.cors import CORSMiddleware  # 原 :1151

print("[office] STEP6 imports fastapi", flush=True)  # 原 :47

# router 装配（routers.gates 顶部 import vision——对应原 :36 的"识图直连模块"加载点）
from .routers import gates, misc, providers, rag, tasks, token_admin

print("[office] STEP3 vision loaded", flush=True)  # 原 :37（vision.analyze_image 已随 routers.gates 导入）

from settings_mgr import token_ok as _token_ok  # 原 :1161（守卫比对统一走它）
from starlette.responses import JSONResponse as _JSONResp  # 原 :1160
from .core import _presented_token
from .routers.gates import _BodyCap  # 原 :875-926（类本体在 gates.py，此处只取类注册）

# 需 token 的写端点（改配置/改服务商/批准/知识库写/上传=改锁或持久化注入面）；GET 读打码值一律放行。
# R79③（评审F P0/评审A·评审B P1）：/rag/ingest·/rag/rebuild 无鉴权=提示注入持久化面，进守护名单；
# R10.2（评审C P2 反向假边界）：/rag/query【移出】管理员名单——提示词三扇门承诺沙箱可达，
#   管理员钥匙它没有=门是假的。改挂二级钥匙 RAG_PROXY_TOKEN（handler 内二认一+频控，见 /rag/query），
#   浏览器前端带管理员 Bearer 同样过（二认一），语义与 /vision 完全同款。
# R79 补（hy4 自检：名单外写端点自查）：/files/save 直写 mia_home/files/（与沙箱共享卷）入守；
#   前端 providerApi.saveFile 同步带 Bearer（管理员的浏览器有钥匙，助手没有=改不动）。
# /threads/title（hy4 低危项）：无鉴权可往任意线程写垃圾标题+白烧 LLM，入守；前端 ChatProvider 同步带 token。
_TOKEN_GUARDED = ("/settings/", "/providers/", "/approvals", "/rag/ingest", "/rag/rebuild", "/files/save", "/threads/title", "/skills/rehash")  # 原 :1171
# R80 续（评审B 旁路实锤+评审C P1 收口）：langgraph auth 罩不到 office 路由（实测 office 路由 200 直通），
# 沙箱虽已出 mia 网，但 Docker Desktop 所有容器都能解析 host.docker.internal → 宿主回环 → 2024 发布口
# （实测沙箱 curl host.docker.internal:2024/settings=200）。敏感【读面】也进 token 门：
# 配置全貌（打码）/服务商表/任务文本/线程用量/RAG 库。
# R10.3（评审D 唯一未修 + 评审B ⚪F）：/models/all /usage/today /stats 三统计端点补齐——
# 前端 providerApi 早已带 Bearer（评审B 51 实证），只差端点门，凑齐读面全收口。
_GET_GUARDED = ("/settings", "/providers", "/tasks/list", "/context/", "/rag/", "/models/all", "/usage/today", "/stats", "/skills")  # 原 :1178
# 读面豁免：token 状态（bootstrap 首部署没钥匙也能看到"先生成密钥"）、webhook（w 内部钥匙自证）、health
_GET_EXEMPT = ("/settings/token/status", "/tasks/webhook", "/health")  # 原 :1180


async def api_token_guard(request, call_next):
    """R10 修二·统一 token 门（原 :1300-1316，原以 @app.middleware("http") 挂载）。
    （体积早拒已由 _BodyCap 纯 ASGI 中间件接管——chunked 无头场景它也罩得住，此处不再重复。）"""
    m = request.method.upper()
    path = request.url.path
    guarded = False
    if m in ("POST", "PUT", "PATCH", "DELETE") and path.startswith(_TOKEN_GUARDED) and path != "/settings/token":
        guarded = True
    elif m == "GET" and path.startswith(_GET_GUARDED) and not path.startswith(_GET_EXEMPT):
        guarded = True
    if guarded:
        # R79③（评审F P0）：fail-closed。原实现"未配 token 则整个守卫跳过"=新部署默认失守
        # （沙箱一条 POST /settings/general 改 confirmLevel=full 即全开，实测复现 200）。
        # 现未配置时写端点一律 401，首设只走 /settings/token（X-Bootstrap 激活码，R10 修二）——首部署须先生成密钥。
        if not _token_ok(_presented_token(request)):
            return _JSONResp({"ok": False, "error": "需要管理员密钥（改设置/服务商/批准/知识库写入是管理员的权柄，助手无此钥匙）"}, status_code=401)
    return await call_next(request)


def create_app() -> FastAPI:
    """装配 app（保持原 office.py 的中间件叠放顺序与路由注册顺序，语义与原版一致）。

    中间件顺序（后 add 的在外层；原文件顺序 :929 → :1300 → :1318）：
        CORS（最外）→ api_token_guard → _BodyCap（最内）→ 路由

    路由注册顺序约束：token_admin 必须先于 providers——
    POST /settings/token（实名路由）必须抢在 POST /settings/{section}（路径参数）之前注册，
    否则首设/轮换会被 {section} 路由吞掉（原源码序即如此：:1333 早于 :1633）。
    """
    _app = FastAPI(title="后台任务队列", version="1.0")  # 原 :48

    _app.add_middleware(_BodyCap)  # 原 :929（纯 ASGI 体积闸：/vision 8MB、/codebuddy 与 /rag/query 2MB）

    _app.middleware("http")(api_token_guard)  # 原 :1300 的 @app.middleware("http")

    # R68 P0（评审 A 面）：CORS 从 * 收紧——只放行本机/局域网来源的前端页面（dev:3000、:2024 自带页）。
    # 服务端到服务端（助手 curl、webhook、compose 内部）不经浏览器 CORS，不受影响。
    _app.add_middleware(  # 原 :1318-1324
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$",
        allow_methods=["*"], allow_headers=["*"],
        # R10.5（XSS L2，官方建议+LibreChat 等主流开源模式）：httpOnly Cookie 跨源携带需要 credentials
        allow_credentials=True,  # R10.8g：Cookie 模式必须；401 响应也要带跨域头
    )

    _app.include_router(token_admin.router)  # 必须最先（/settings/token 抢在 /settings/{section} 前）
    _app.include_router(providers.router)
    _app.include_router(rag.router)
    _app.include_router(gates.router)
    _app.include_router(tasks.router)
    _app.include_router(misc.router)
    return _app


app = create_app()  # 供装配壳 `from office.app import app` 使用（原 :48 模块级 app 的等价物）


if __name__ == "__main__":
    import uvicorn  # 原 :1900
    uvicorn.run(app, host="127.0.0.1", port=2024, log_level="info")  # 原 :1901
