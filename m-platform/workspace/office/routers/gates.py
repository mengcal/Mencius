"""
office.routers.gates —— _BodyCap 中间件类 + /vision + /codebuddy 代理门（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :73-76     VisionReq
- :727-772   /vision 钥匙/双窗频控/计量常量 + _vision_usage_log
- :775-823   POST /vision（第一扇代理门）
- :826-872   CodeBuddy 代理层常量 + _VISION_MAX_BODY + _send_413
- :875-926   _BodyCap（纯 ASGI 体积闸中间件【类】；注册动作原 :929 `app.add_middleware(_BodyCap)`
             移到 app.py 的 create_app 内——app.py 不重复定义类）
- :953-1103  _cb_allowed_models / _cb_rate_ok / _cb_usage_log + POST /codebuddy/chat/completions（第二扇代理门）
（第三扇代理门 = /rag/query，在 routers/rag.py：RAG_PROXY_TOKEN 二认一 + 双窗 60s≤30 + 2MB 帽）

三扇门同型防护对照（各自独立频控/计量/钥匙校验，互不挤兑）：
- /vision      ：X-Proxy-Key=VISION_PROXY_TOKEN 或 Bearer 管理员密钥；双窗 60s≤20；解析后 nbytes 8MB 帽
- /codebuddy/* ：Bearer / X-Proxy-Key=CODEBUDDY_PROXY_TOKEN；单窗 60s≤30；并发信号量 3；2MB 帽；模型白名单
- /rag/query   ：X-Proxy-Key=RAG_PROXY_TOKEN 或 Bearer 管理员密钥；双窗 60s≤30；_BodyCap 2MB 帽
"""
import asyncio
import os
import time

from pathlib import Path

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from vision import analyze_image  # 原 :36（识图直连模块，绕过 deepagents，快）

from settings_mgr import token_ok as _token_ok  # 原 :1161（管理员 Bearer 二认一）

from ..core import BASE, _JSONResp, _ck, _rate_ok, _rotate_log, _secrets_dir

router = APIRouter()


class VisionReq(BaseModel):
    image_path: str = ""
    image_b64: str = ""
    question: str = "请描述这张图片的内容"


# ===== R10 修一：/vision 二级钥匙 + 独立频控 + 计量（评审A 修法 C' + 评审C 成本面）=====
# 修三把视觉工人岗的识图地址从容器内网 workplatform:8000 改成宿主回环 host.docker.internal:2024，
# 这条路径绕开了 office 的统一 token 门（auth.py 对 /vision 整条放行），等于给沙箱留了直连识图口。
# 对策：给 /vision 单独配一把【代理钥匙】VISION_PROXY_TOKEN（二认一，写法沿用 codebuddy 代理层同款模式），
# 其全部价值=消耗识图额度，无任何管理权限；钥匙只在宿主 env 与沙箱 env 里，不进镜像、不进源码。
# R10.2（hy4 ③-1 + 评审A战果二 + 评审C P3 三家同抓）：钥匙未配=fail-CLOSED（旧版放行=半裸奔，
# 与 codebuddy 语义相反）。"宿主本地调试"场景不再靠 fail-open 兜——管理员 token 二认一照样能过。
_VISION_HITS_PROXY: list = []    # 代理钥匙窗（沙箱工人岗）——60s ≤20
_VISION_HITS_ADMIN: list = []    # 管理员 Bearer 窗（管理员浏览器）——R10.3（评审B 四-4②）分窗：
                                 # 沙箱刷爆自己的窗不会饿死管理员在设置页点的识图
_VISION_RATE_WINDOW = 60.0
_VISION_RATE_MAX = 20
# 计量日志落 secrets 侧（修四①同目录）：被审计方不可写，账本不被自己抹平
_VISION_USAGE_LOG = _secrets_dir() / "vision_usage.jsonl"


def _vision_usage_log(status: int, nbytes: int, src: str = "", mode: str = "") -> None:
    """计量（仿 _cb_usage_log）：每次调用（含 401/413/429/502）追加一行。
    R10.2（hy4 ③-4）：补 src（钥匙来源 proxy-key/admin-bearer/none）与 mode（path/b64）——
    出事能区分"谁在用哪条路刷"。不落任何钥匙材料。
    R10.3：超 10MB 自动滚 .old（评审B 四-4①，磁盘填充无积累）。
    记账是观测面不是闸门：写盘失败只出声，绝不改变本次调用的结果。"""
    try:
        import datetime as _dt
        import json as _j
        _rotate_log(_VISION_USAGE_LOG)
        _VISION_USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _VISION_USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(_j.dumps({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                              "status": int(status), "bytes": int(nbytes or 0),
                              "src": src[:20], "mode": mode[:10]},
                             ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[vision] 计量日志写入失败：{e}", flush=True)


@router.post("/vision")
async def vision(req: VisionReq = Body(...), request: Request = None):
    """识图直连接口（书生多模态，绕过 deepagents，快）。
    给 image_path 或 image_b64 + question。
    R10.3 门序（采纳 评审A 意见 swap，与 codebuddy 对齐）：体积 → 钥匙 → 频控 → 干活。
    频控的本意是保护上游资源（识图=真金白银的模型调用）——验不过钥匙的请求根本碰不到上游，
    不该消耗保护上游的配额（匿名挤兑面）；401 只花一次 hmac（微秒级），账本有 10MB 旋转兜底。
    钥匙二认一 fail-closed：X-Proxy-Key==VISION_PROXY_TOKEN（沙箱，走代理窗）
    或 Bearer==管理员 token（管理员浏览器，走管理员窗——分窗，沙箱刷不爆管理员的窗）。
    """
    try:
        import json as _j
        nbytes = len(_j.dumps({"image_path": req.image_path, "image_b64": req.image_b64,
                               "question": req.question}, ensure_ascii=False).encode("utf-8"))
    except Exception:
        nbytes = 0
    mode = "path" if (req.image_path or "").strip() else ("b64" if (req.image_b64 or "").strip() else "none")
    # R10.2（评审A 战果一）：解析后 nbytes 复核（chunked 场景兜底，主体闸在 _BodyCap）；
    # R10.4（评审C P3-3）：vision 独立 8MB 帽（Retina 大图 b64 后 4MB+，2MB 误伤合法请求）
    if nbytes > _VISION_MAX_BODY:
        _vision_usage_log(413, nbytes, "size-gate", mode)
        return _JSONResp({"error": f"请求体过大（{nbytes} B > {_VISION_MAX_BODY} B）"}, status_code=413)
    vtok = os.environ.get("VISION_PROXY_TOKEN", "")
    ah = str(request.headers.get("authorization") or "") if request else ""
    bearer = ah[7:].strip() if ah.lower().startswith("bearer ") else ""
    xpk = str(request.headers.get("x-proxy-key") or "") if request else ""
    src = "none"
    if vtok and _ck(xpk, vtok):
        src = "proxy-key"
    elif bearer and _token_ok(bearer):  # R10.6：guard 模式下进程不持明文，管理员比对走守卫
        src = "admin-bearer"
    else:
        _vision_usage_log(401, nbytes, "rejected", mode)
        return _JSONResp({"error": "识图需钥匙（X-Proxy-Key=代理钥匙 或 Authorization: Bearer=管理员密钥）"},
                         status_code=401)
    if not _rate_ok(_VISION_HITS_PROXY if src == "proxy-key" else _VISION_HITS_ADMIN,
                    _VISION_RATE_WINDOW, _VISION_RATE_MAX):
        _vision_usage_log(429, nbytes, src, mode)
        return _JSONResp({"error": f"识图限流：每 {int(_VISION_RATE_WINDOW)} 秒最多 {_VISION_RATE_MAX} 次"},
                         status_code=429)
    # R68 修 评审A（中危阻塞）：识图 20s 级同步调用不再坐在事件循环里——丢线程池
    # R10.2（hy4 ③-4：上游异常原来直接 500 且不记账）：收口成 502 并记计量
    try:
        result = await asyncio.to_thread(analyze_image, req.image_path, req.image_b64, req.question)
    except Exception as e:
        _vision_usage_log(502, nbytes, src, mode)
        return _JSONResp({"error": f"识图上游失败：{type(e).__name__}"}, status_code=502)
    _vision_usage_log(200, nbytes, src, mode)
    return {"result": result}


# ===== R82 CodeBuddy 代理层（评审C 方案 a·密钥出笼）=====
# 背景：R80 把真魔搭 key 撤出沙箱 env（助手 printenv 就能读走），但沙箱里的 CodeBuddy CLI
# 要干活仍需一个 OpenAI 兼容端点。本端点=唯一授权通道：沙箱工人岗带【代理钥匙】(X-Proxy-Key，
# 其全部价值=消耗所配模型的免费额度，无其他权限) 调 /codebuddy/chat/completions，
# 真 API key 由 workplatform 进程 env 注入、只活在这个进程里。
# 目标地址取 env 固定值（管理员侧配置，与 SANDBOX_EXEC_URL 同性质），不由任何请求输入拼装。

# ── R82 补强（hy4 第一轮审查挑的刺，逐条补）：白名单 / 夹取 / 体积 / 并发+频控 / 计量 ──
_CB_MAX_TOKENS = 8192            # ②单请求 max_tokens 上限：缺失或超限一律夹到这个值
_CB_MAX_BODY = 2 * 1024 * 1024   # ③请求体序列化上限 2MB（防大上下文/大图白烧上游额度）
_CB_SEM = asyncio.Semaphore(3)   # ④上游并发闸门：同时最多 3 个在飞请求（上游账号扛不住无限并发）
_CB_HITS: list = []              # ④滑动窗口时间戳（stdlib time 列表，60s 内 ≤30 次）
_CB_RATE_WINDOW = 60.0
_CB_RATE_MAX = 30
# ⑤计量日志路径（相对路径按 BASE 解析，与 _TASKS_FILE 同款）
# R10 修四①（评审C）：账本挪出被审计方可写区——默认落宿主 secrets 卷（与激活码同目录），
# 沙箱/工人岗摸不到这个卷，烧了多少额度就赖不掉也抹不平；env 未设时回落 BASE/mia_home/logs 保本地开发。
_cb_log_env = os.environ.get("CODEBUDDY_USAGE_LOG", "").strip()
if _cb_log_env:
    _CB_USAGE_LOG = Path(_cb_log_env)
elif os.environ.get("MIA_SECRETS_PATH", "").strip():
    _CB_USAGE_LOG = _secrets_dir() / "codebuddy_usage.jsonl"
else:
    _CB_USAGE_LOG = BASE / "mia_home" / "logs" / "codebuddy_usage.jsonl"
if not _CB_USAGE_LOG.is_absolute():
    _CB_USAGE_LOG = BASE / _CB_USAGE_LOG


# ── R10.3（评审C P2 终局报告）：请求体硬顶——纯 ASGI 层，chunked 慢灌也进不来 ──
# R10.2 的 Content-Length 早拒罩不住无 CL 头的 chunked 上传（8GB 慢灌会在 FastAPI 全量缓冲
# 阶段吃满内存且不需要任何钥匙）。本中间件预排空计数：有 CL 头=秒判 413；chunked 逐块累计，
# 超 _CB_MAX_BODY 直接 413 收场、请求体永远到不了 FastAPI 的缓冲。
# R10.4（评审C P2 收官轮）：/rag/query 补进体积闸——第三扇钥匙门与 vision/codebuddy 同型，
# r10.2 开门时没跟上同型面排查（"小 body 是合法请求的形态，不是攻击者会遵守的约束"）。
# R10.4（评审C P3-3）：vision 独立 8MB 帽——Retina 截图 PNG→b64 后 4MB+，2MB 会误伤合法大图；
# codebuddy（纯文本）与 rag/query（q_vec 数组，几 KB）维持 2MB。
_VISION_MAX_BODY = 8 * 1024 * 1024


async def _send_413(send):
    import json as _j413
    data = _j413.dumps({"error": "请求体过大（超过端点体积上限），chunked 分块同样拒收"},
                       ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data})


class _BodyCap:
    _PATHS = ("/vision", "/codebuddy", "/rag/query")

    @staticmethod
    def _cap(path: str) -> int:
        return _VISION_MAX_BODY if path.startswith("/vision") else _CB_MAX_BODY

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = str(scope.get("path") or "")
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or not path.startswith(self._PATHS)):
            return await self.app(scope, receive, send)
        cap = self._cap(path)
        try:
            cl = int(dict(scope.get("headers") or []).get(b"content-length", b"0") or 0)
        except Exception:
            cl = 0
        if cl > cap:
            await _send_413(send)
            return
        body, over, disconnected = bytearray(), False, False
        while True:
            msg = await receive()
            t = msg.get("type")
            if t == "http.disconnect":
                disconnected = True
                break
            body += msg.get("body") or b""
            if len(body) > cap:
                over = True
                break
            if not msg.get("more_body", False):
                break
        if disconnected:
            return
        if over:
            await _send_413(send)
            return
        msgs = [{"type": "http.request", "body": bytes(body), "more_body": False},
                {"type": "http.disconnect"}]
        it = iter(msgs)

        async def replay():
            try:
                return next(it)
            except StopIteration:
                return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


# 原 :929 `app.add_middleware(_BodyCap)` —— 注册动作移至 app.py 的 create_app()（保持中间件叠放顺序）

def _cb_allowed_models() -> set:
    """R82 补强①：model 白名单。配了 CODEBUDDY_ALLOWED_MODELS（逗号分隔）就认它；
    没配则回落到单模型 env CODEBUDDY_MODEL（默认 Qwen/Qwen3.8-Flash-Next）。
    作用：沙箱工人岗改 body.model 也换不动上游模型——这把钥匙的全部价值就是消耗所配模型的免费额度，
    换模型=拿它去烧别的（付费）额度，必须在代理层挡死。"""
    raw = os.environ.get("CODEBUDDY_ALLOWED_MODELS", "")
    if raw.strip():
        return {m.strip() for m in raw.split(",") if m.strip()}
    return {(os.environ.get("CODEBUDDY_MODEL", "Qwen/Qwen3.8-Flash-Next") or "").strip()
            or "Qwen/Qwen3.8-Flash-Next"}


def _cb_rate_ok() -> bool:
    """R82 补强④：滑动窗口限流（stdlib time 时间戳列表，60s 内 ≤30 次）。
    单线程事件循环下"清窗口→判满→追加"这一步不会被切走，无需额外锁。"""
    now = time.time()
    while _CB_HITS and now - _CB_HITS[0] > _CB_RATE_WINDOW:
        _CB_HITS.pop(0)
    if len(_CB_HITS) >= _CB_RATE_MAX:
        return False
    _CB_HITS.append(now)
    return True


def _cb_usage_log(model: str, status: int, stream: bool, nbytes: int) -> None:
    """R82 补强⑤：计量——每次调用（含被拒的 401/403/413/429）追加一行 JSON。
    记账是观测面不是闸门：写盘失败只出声，绝不改变本次调用的结果。"""
    try:
        import datetime as _dt
        import json as _j
        _rotate_log(_CB_USAGE_LOG)
        _CB_USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _CB_USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(_j.dumps({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                              "model": str(model or "")[:120], "status": int(status),
                              "stream": bool(stream), "bytes": int(nbytes or 0)},
                             ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[codebuddy-proxy] 计量日志写入失败：{e}", flush=True)


@router.post("/codebuddy/chat/completions")
async def codebuddy_proxy(request: Request):
    import hmac as _hmac2
    import httpx as _hx
    import json as _j
    from starlette.responses import StreamingResponse as _Stream
    proxy_tok = os.environ.get("CODEBUDDY_PROXY_TOKEN", "")
    up_base = os.environ.get("CODEBUDDY_BASE_URL", "")
    up_key = os.environ.get("CODEBUDDY_API_KEY", "")
    if not proxy_tok:
        _cb_usage_log("", 403, False, 0)
        return _JSONResp({"error": "代理层未配置（CODEBUDDY_PROXY_TOKEN 缺失）"}, status_code=403)  # fail-closed
    # 两种头都认：CodeBuddy CLI 原生发 Authorization: Bearer <key>（沙箱里填的是代理钥匙）；手动调用可用 X-Proxy-Key
    ah = str(request.headers.get("authorization") or "")
    bearer = ah[7:].strip() if ah.lower().startswith("bearer ") else ""
    xpk = str(request.headers.get("x-proxy-key") or "")
    # R10.2（hy4 ③-10）：比对统一走 _ck（bytes 版 compare_digest）——非 ASCII 头不再 TypeError 炸 500
    if not (_ck(bearer, proxy_tok) or _ck(xpk, proxy_tok)):
        _cb_usage_log("", 401, False, 0)
        return _JSONResp({"error": "代理钥匙不匹配"}, status_code=401)
    if not (up_base and up_key):
        _cb_usage_log("", 503, False, 0)
        return _JSONResp({"error": "上游未配置（CODEBUDDY_BASE_URL/API_KEY）"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        _cb_usage_log("", 400, False, 0)
        return _JSONResp({"error": "请求体需为 JSON"}, status_code=400)
    # R82 补强③：体积闸门先于频控/白名单——超大请求不该吃掉频控配额，也不该进白名单比对
    try:
        nbytes = len(_j.dumps(body, ensure_ascii=False).encode("utf-8"))
    except Exception:
        nbytes = 0
    if nbytes > _CB_MAX_BODY:
        _cb_usage_log(str(body.get("model") or ""), 413, bool(body.get("stream")), nbytes)
        return _JSONResp({"error": f"请求体过大（{nbytes} B > {_CB_MAX_BODY} B）"}, status_code=413)
    # R82 补强④：频控（先挡超频，再放行进并发闸门——超频请求不该占住上游并发票）
    if not _cb_rate_ok():
        _cb_usage_log(str(body.get("model") or ""), 429, bool(body.get("stream")), nbytes)
        return _JSONResp({"error": f"代理限流：每 {int(_CB_RATE_WINDOW)} 秒最多 {_CB_RATE_MAX} 次"}, status_code=429)
    # R82 补强①：model 白名单（model 缺失=空串，同样过不了——fail-closed）
    model = str(body.get("model") or "")
    if model not in _cb_allowed_models():
        _cb_usage_log(model, 403, bool(body.get("stream")), nbytes)
        return _JSONResp({"error": f"模型未授权：{model[:80] or '(空)'}（白名单见 CODEBUDDY_ALLOWED_MODELS）"},
                         status_code=403)
    # R82 补强②：max_tokens 夹取（缺失/非整数/非正数/超上限 → 8192）
    mt = body.get("max_tokens")
    if not isinstance(mt, int) or isinstance(mt, bool) or mt <= 0 or mt > _CB_MAX_TOKENS:
        body["max_tokens"] = _CB_MAX_TOKENS
    stream = bool(body.get("stream"))
    target = up_base.rstrip("/") + "/chat/completions"
    fwd_headers = {"Authorization": f"Bearer {up_key}", "Content-Type": "application/json"}
    # R82 补强④：并发闸门。流式请求的票不在本函数归还——交给 _sse 收尾时还，
    # 否则票在返回 StreamingResponse 时就放了，闸门只罩住握手、罩不住整段流。
    await _CB_SEM.acquire()
    holding = True
    try:
        if stream:
            client = _hx.AsyncClient(timeout=120)
            try:
                req0 = client.build_request("POST", target, json=body, headers=fwd_headers)
                resp0 = await client.send(req0, stream=True)
            except Exception as e:
                # R82 补强⑥：异常路径兜底 aclose（build_request/send 抛错时 client 无人回收=连接泄漏）
                try:
                    await client.aclose()
                except Exception:
                    pass
                _cb_usage_log(model, 502, True, nbytes)
                print(f"[codebuddy-proxy] 流式转发失败：{type(e).__name__} {e}", flush=True)
                return _JSONResp({"error": f"上游转发失败：{type(e).__name__}"}, status_code=502)
            if resp0.status_code != 200:
                await resp0.aread()
                await resp0.aclose()
                await client.aclose()
                _cb_usage_log(model, 502, True, nbytes)
                print(f"[codebuddy-proxy] 流式上游返回 {resp0.status_code}", flush=True)
                return _JSONResp({"error": f"上游返回 {resp0.status_code}"}, status_code=502)

            async def _sse():
                try:
                    async for chunk in resp0.aiter_bytes():
                        yield chunk
                finally:
                    await resp0.aclose()
                    await client.aclose()
                    _CB_SEM.release()

            holding = False  # 票已移交 _sse
            _cb_usage_log(model, 200, True, nbytes)
            return _Stream(_sse(), media_type="text/event-stream")
        async with _hx.AsyncClient(timeout=120) as client:
            try:
                r = await client.post(target, json=body, headers=fwd_headers)
            except Exception as e:
                _cb_usage_log(model, 502, False, nbytes)
                print(f"[codebuddy-proxy] 转发失败：{type(e).__name__} {e}", flush=True)
                return _JSONResp({"error": f"上游转发失败：{type(e).__name__}"}, status_code=502)
            try:
                payload = r.json()
            except Exception:
                _cb_usage_log(model, 502, False, nbytes)
                print(f"[codebuddy-proxy] 上游响应非 JSON（{r.status_code}）", flush=True)
                return _JSONResp({"error": "上游响应非 JSON"}, status_code=502)
            _cb_usage_log(model, r.status_code, False, nbytes)
            return _JSONResp(payload, status_code=r.status_code)
    finally:
        if holding:
            _CB_SEM.release()
