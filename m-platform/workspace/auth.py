# -*- coding: utf-8 -*-
"""auth.py — langgraph 原生 API 鉴权（R80 评审C b 方案·纵深防御）

背景：token 门是 office FastAPI 的 middleware，只罩 office 路由；langgraph 原生路由
（/threads·/runs·/assistants·store·/{graph} 流式等）由 langgraph-api 服务器自己处理，
零鉴权——R80 沙箱物理出网后实际威胁面已死（沙箱 curl 不到平台），此为第二层纵深：
同网其他容器/本机进程即使摸到原生 API 也要管理员密钥。

原则与 office 同一真源：settings_mgr.token_ok（密钥只在 .settings_secrets，沙箱没有）。
- office 自带路由（/settings /providers /approvals /tasks /files /vision /codebuddy /config /health）放行——
  它们各有自己的门（统一 token 门 fail-closed；/tasks/webhook 有 w 内部钥匙；healthcheck 无密钥）。
  若未来 office 路由也要过这里，改豁免清单即可（保持单层门职责清晰）。
- 原生 API 一律 Bearer == 管理员密钥，否则 401（fail-closed，未配置密钥时全拒）。
- 平台基础设施 /ok /info /openapi.json /docs /redoc 放行（无敏感面，供健康检查与文档）。
- @auth.on 全放行：能过 authenticate 的（真密钥或 office 豁免）即有权（助手/沙箱过不来）。
"""
from langgraph_sdk import Auth
from starlette.requests import Request

from settings_mgr import token_ok
from internal_key import INTERNAL_KEY as internal_key  # R10.8：进程身份钥匙（模块级单例）

auth = Auth()

# office 自带路由前缀 + 平台无敏感基础设施（office 路由实测在 langgraph auth 罩外——此处清单是
# 双保险+防未来架构变化；R80 续按 评审C P1 补精确路径变体，避免"尾斜杠一字之差"坑下一轮）
_OFFICE_ALLOW = (
    "/settings", "/settings/", "/providers", "/providers/", "/approvals", "/approvals/",
    "/tasks", "/tasks/", "/files", "/files/", "/vision", "/config", "/health",
    "/rag", "/rag/", "/office",
    # R10 修四③（评审D 小项）：/codebuddy 提前入册——代理层自带代理钥匙门（X-Proxy-Key），
    # 若将来 office 路由真进了 auth 罩，缺这一条会让沙箱 CodeBuddy CLI 直接断链（自检都跑不动）。
    "/codebuddy", "/codebuddy/",
    # R10.2（评审A 观察②）："/threads/title" 不再放前缀——startswith 会撞原生 GET /threads/{id}
    # 当 id=="title…"（thread_id 虽需管理员钥匙才建得出、无实际碰撞面，但豁免清单=双保险，
    # 双保险的每一行也不该多罩一寸）。office 真路由是 POST /threads/title，按精确路径放行。
    "/ok", "/info", "/openapi.json", "/docs", "/redoc",
)
_EXACT_ALLOW = ("/threads/title",)


@auth.authenticate
async def authenticate(request: Request) -> dict:
    path = request.url.path
    # R10.6：office 进程在 guard 模式下不持明文钥匙，它对原生 API 的进程内合法调用
    # （派活/汇报/起标题）需要一个"进程身份"通道。R10.8（评审C P0-2/评审B B/评审E P1-1）：
    # 网络位置豁免（源 127.0.0.1+端口 8000）被打穿——容器内助手的 shell 同样是回环源，
    # 一条 curl 即免 token 读全部对话。现改【进程身份】为主判据：X-Internal-Key 必须
    # 等于同进程 internal_key.INTERNAL_KEY（启动时随机生成，只活在该进程内存里，
    # 助手的 shell 进程 env 继承拿不到）——网络回环保留为第二道条件。
    import hmac as _hk
    if (request.client and request.client.host in ("127.0.0.1", "::1")
            and _hk.compare_digest(str(request.headers.get("x-internal-key") or ""),
                                   str(internal_key))):
        return {"identity": "internal-loopback", "permissions": ["*"]}
    if path in _EXACT_ALLOW or path.startswith(_OFFICE_ALLOW):
        return {"identity": "office-route", "permissions": ["*"]}
    ah = request.headers.get("authorization", "")
    # R10.3：x-api-key 认头（langgraph_sdk 客户端默认发它）。
    # R10.5：HttpOnly Cookie（浏览器登录后自动携带）。
    # R10.8d（管理员实测 401 根因）：凭证优先级修正——X-Api-Key 在本部署里是 LangSmith 的 key
    # （前端 SDK 恒发，非管理员凭证），它非空会**挡住 Cookie 兜底**导致已登录用户仍 401。
    # 正确顺序：Bearer/x-token（显式管理员凭证）→ Cookie（浏览器登录态）→ x-api-key（最后兜底）。
    bearer = ah[7:].strip() if ah.lower().startswith("bearer ") else ""
    tok = bearer or (request.headers.get("x-token") or "")
    if not tok:
        try:
            tok = request.cookies.get("m_admin_token") or ""
        except Exception:
            tok = ""
    if not tok:
        tok = request.headers.get("x-api-key") or ""
    if not token_ok(tok):
        raise Auth.exceptions.HTTPException(status_code=401, detail="原生 API 需要管理员密钥（R80 纵深）")
    return {"identity": "admin", "permissions": ["*"]}


@auth.on
async def allow_all(ctx, value):  # 通过 authenticate 的请求即放行（详见文件头原则）
    return True
