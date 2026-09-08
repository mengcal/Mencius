"""
office.routers.rag —— RAG 知识库存储层 + 五个 /rag/* 端点（APIRouter）
=====================================================================
来源：D:\\m\\workspace\\office.py（1901 行）拆分。本文件对应原行号段：
- :168-175  存储层说明 + _RAG_VEC / _RAG_DIM
- :178-236  _rag_pg / _rag_migrate_json / _rag_load
- :270-276  /rag/query 独立滑动窗口常量（_RAG_HITS_PROXY/_RAG_HITS_ADMIN/_RAG_RATE_WINDOW/_RAG_RATE_MAX）
- :280-285  _rag_cos
- :288-460  POST /rag/ingest、POST /rag/query、GET /rag/list、GET /rag/stats、POST /rag/rebuild

注：原 :1148 的 `import json as _json` 在原文件里延迟到文件后部才出现（先定义后导入的隐式依赖），
本模块提到顶部显式导入，行为等价。
"""
import asyncio
import json as _json  # 原 :1148（提到顶部）
import os

from fastapi import APIRouter, Body, Request

from settings_mgr import token_ok as _token_ok  # 原 :1161（/rag/query 管理员 Bearer 二认一）

from ..core import BASE, _JSONResp, _ck, _rate_ok

router = APIRouter()

# ===== RAG 知识库存储层（R43 升级 pgvector，2026-08-31 作者）=====
# 架构：嵌入仍由前端浏览器直调管理员本机 Ollama（localhost:11434），服务器只管存取与检索。
# 存储：PG + pgvector（compose 镜像 pgvector/pgvector:pg16，数据卷 pg_data 延续）——真·生产级向量检索。
# 兜底：PG/vector 不可用时自动回落 mia_home/rag_vectors.json（绝不挡功能），恢复后自动续用。
# 相关度语义不变：1 - 余弦距离（pgvector 的 <=> 操作符）。

_RAG_VEC = BASE / "mia_home" / "rag_vectors.json"   # 兜底存储 + 一次性迁移源
_RAG_DIM = 1024  # bge-large/mxbai 均 1024 维；2026-09-02 换 qwen3-embedding:0.6b 实测也=1024，表结构零改动（配置页 rag.embeddingModel 可再换，维度不符时重建需先改此列）


def _rag_pg():
    """PG 连接（短连接，量小够用）；PG/vector 不可用返回 None（调用方走 JSON 兜底）。"""
    try:
        import psycopg2, os
        uri = os.environ.get("DATABASE_URI") or ""  # R69：弱口令兜底删——宁报错（回落 JSON）不默认连
        if not uri:
            return None
        conn = psycopg2.connect(uri, connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS rag_chunks("
                "id bigserial primary key, name text not null, idx int not null default 0,"
                "text text not null default '', lang text not null default 'zh',"
                f"vec vector({_RAG_DIM}))"
            )
        conn.commit()
        return conn
    except Exception as e:
        print(f"[rag] PG 不可用，回落 JSON：{e}", flush=True)
        return None


def _rag_migrate_json(conn):
    """一次性：把旧 rag_vectors.json 的切片搬进 PG（搬完原文件改名 .migrated 留证）。"""
    with conn.cursor() as cur:
        cur.execute("select count(*) from rag_chunks")
        if cur.fetchone()[0] > 0:
            return
    if not _RAG_VEC.exists():
        return
    try:
        db = _json.loads(_RAG_VEC.read_text(encoding="utf-8"))
        moved = 0
        with conn.cursor() as cur:
            for c in db.get("chunks", []):
                vec = [float(x) for x in c.get("vec", [])]
                if len(vec) != _RAG_DIM:
                    continue
                cur.execute(
                    "insert into rag_chunks(name, idx, text, lang, vec) values (%s,%s,%s,%s,%s::vector)",
                    (c["name"], c.get("idx", 0), c["text"], c.get("lang", "zh"), str(vec)))
                moved += 1
        conn.commit()
        if moved:
            _RAG_VEC.rename(_RAG_VEC.with_suffix(".json.migrated"))
            print(f"[rag] 旧 JSON 迁移完成：{moved} 片 → PG", flush=True)
    except Exception as e:
        print(f"[rag] JSON 迁移失败（忽略，原文件保留）：{e}", flush=True)


def _rag_load():
    """JSON 兜底读取（PG 不可用时用）。"""
    if _RAG_VEC.exists():
        try:
            return _json.loads(_RAG_VEC.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"chunks": []}


# ── R10 修四④：/rag/query 独立滑动窗口（60s ≤30）──
# codebuddy/vision/rag 窗口各记各的时间戳：任一被刷爆不会把另两个一起拖死（互不挤兑）。
# R10.3（评审B 四-4②）：分代理窗/管理员窗——沙箱刷爆检索不饿死管理员设置页的检索按钮。
_RAG_HITS_PROXY: list = []
_RAG_HITS_ADMIN: list = []
_RAG_RATE_WINDOW = 60.0
_RAG_RATE_MAX = 30


def _rag_cos(a, b):
    import math as _math
    dot = sum(x * y for x, y in zip(a, b))
    na = _math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = _math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


@router.post("/rag/ingest")
async def rag_ingest(req: dict = Body(...)):
    """入库（向量由前端嵌入后传来）：{"name": "文档名", "chunks": [{"text": "...", "lang": "zh|en", "vec": [...]}]}"""
    name = (req.get("name") or "").strip()
    chunks = req.get("chunks") or []
    if not name or not chunks:
        return {"error": "需要 name 和 chunks"}
    conn = _rag_pg()
    if conn:
        try:
            _rag_migrate_json(conn)
            with conn.cursor() as cur:
                cur.execute("delete from rag_chunks where name=%s", (name,))
                for i, c in enumerate(chunks):
                    vec = [float(x) for x in c.get("vec", [])]
                    if len(vec) != _RAG_DIM:
                        return {"error": f"向量维度应为 {_RAG_DIM}，收到 {len(vec)}（检查嵌入模型）"}
                    cur.execute(
                        "insert into rag_chunks(name, idx, text, lang, vec) values (%s,%s,%s,%s,%s::vector)",
                        (name, i, str(c.get("text", ""))[:2000], c.get("lang", "zh"), str(vec)))
            conn.commit()
            conn.close()
            return {"ok": True, "name": name, "chunks": len(chunks), "store": "pg"}
        except Exception as e:
            try: conn.close()
            except Exception: pass
            print(f"[rag] PG 入库失败，回落 JSON：{e}", flush=True)
    # JSON 兜底
    clean = [{"name": name, "idx": i, "text": str(c.get("text", ""))[:2000],
              "lang": c.get("lang", "zh"), "vec": [float(x) for x in c.get("vec", [])]}
             for i, c in enumerate(chunks)]
    db = _rag_load()
    db["chunks"] = [c for c in db["chunks"] if c.get("name") != name] + clean
    _RAG_VEC.parent.mkdir(parents=True, exist_ok=True)
    _RAG_VEC.write_text(_json.dumps(db, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "name": name, "chunks": len(clean), "store": "json"}


@router.post("/rag/query")
async def rag_query(req: dict = Body(...), request: Request = None):
    """检索：{"q_vec": [查询向量], "k": 5}（向量前端算好传来）。
    R67：单模型跨语言（rag.embeddingModel），lang 仅收参数不再过滤——旧双模型时代按语言切库的规矩作废。
    R10.2（评审C P2）：门从"管理员 token 独占"改成二级钥匙二认一——
    X-Proxy-Key==RAG_PROXY_TOKEN（沙箱工人岗经宿主回环检索，提示词三扇门之一成真）
    或 Bearer==管理员 token（设置页检索按钮）；都拿不出=401（fail-closed，同 vision 语义）。
    R10.3（评审A swap 意见）：门序=钥匙 → 频控（分窗）。
    R10.4（评审C P2）：体积闸在 _BodyCap（_PATHS 已含 /rag/query，2MB）——"小 body 是合法请求的形态，
    不是攻击者会遵守的约束"，同型钥匙门必须同型防护。"""
    rtok = os.environ.get("RAG_PROXY_TOKEN", "")
    ah = str(request.headers.get("authorization") or "") if request else ""
    bearer = ah[7:].strip() if ah.lower().startswith("bearer ") else ""
    xpk = str(request.headers.get("x-proxy-key") or "") if request else ""
    if rtok and _ck(xpk, rtok):
        src = "proxy-key"
    elif bearer and _token_ok(bearer):  # R10.6：guard 模式下进程不持明文，管理员比对走守卫
        src = "admin-bearer"
    else:
        return _JSONResp({"error": "检索需钥匙（X-Proxy-Key=代理钥匙 或 Authorization: Bearer=管理员密钥）"},
                         status_code=401)
    # R10 修四④：独立滑动窗口（60s ≤30）——向量检索是 CPU/IO 活，被刷爆会拖垮整个平台。
    if not _rate_ok(_RAG_HITS_PROXY if src == "proxy-key" else _RAG_HITS_ADMIN,
                    _RAG_RATE_WINDOW, _RAG_RATE_MAX):
        return _JSONResp({"error": f"检索限流：每 {int(_RAG_RATE_WINDOW)} 秒最多 {_RAG_RATE_MAX} 次"},
                         status_code=429)
    qv = [float(x) for x in (req.get("q_vec") or [])]
    if not qv:
        return {"error": "需要 q_vec（前端嵌入好的查询向量）"}
    conn = _rag_pg()
    if conn:
        # R79 补（hy4 自检：读端点不许藏写副作用）：旧版此处调 _rag_migrate_json（insert+rename）——
        # 与"query=读面不拦"的表述不符。迁移触发点已收敛到 /rag/ingest（原 :298）与 rebuild 两个写端点（均在守），
        # json 存量数据在下次上传/重建时照常入库，查询路径保持真只读。
        try:
            conn.close()
        except Exception:
            pass
        try:
            # R69 双实现合并：SQL 单一源在 rag_engine.search_vectors
            from rag_engine import search_vectors
            rows = search_vectors(qv, int(req.get("k", 5)))
            return {"ok": True, "store": "pg", "results": [
                {"score": round(float(s), 4), "name": n, "text": t[:800]} for n, t, s in rows]}
        except Exception as e:
            print(f"[rag] PG 检索失败，回落 JSON：{e}", flush=True)
    db = _rag_load()
    scored = sorted(((_rag_cos(qv, c["vec"]), c) for c in db["chunks"]), key=lambda x: -x[0])[:int(req.get("k", 5))]
    return {"ok": True, "store": "json", "results": [
        {"score": round(s, 4), "name": c["name"], "text": c["text"][:800]}
        for s, c in scored]}


@router.get("/rag/list")
async def rag_list():
    """全量（含向量，前端本地检索用；PG 模式返回不含向量的切片列表）"""
    conn = _rag_pg()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select name, idx, text, lang from rag_chunks order by name, idx")
                rows = cur.fetchall()
            conn.close()
            return {"chunks": [{"name": n, "idx": i, "text": t, "lang": l} for n, i, t, l in rows]}
        except Exception:
            try: conn.close()
            except Exception: pass
    return _rag_load()


@router.get("/rag/stats")
async def rag_stats():
    conn = _rag_pg()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select name, count(*) from rag_chunks group by name order by name")
                rows = cur.fetchall()
                cur.execute("select count(*) from rag_chunks")
                total = cur.fetchone()[0]
            conn.close()
            return {"chunks": total, "docs": {n: c for n, c in rows}, "store": "pg"}
        except Exception:
            try: conn.close()
            except Exception: pass
    db = _rag_load()
    names: dict = {}
    for c in db["chunks"]:
        names[c["name"]] = names.get(c["name"], 0) + 1
    return {"chunks": len(db["chunks"]), "docs": names}


_RAG_REBUILDING = False

@router.post("/rag/rebuild")
async def rag_rebuild():
    """R67（管理员 09-02）：换嵌入模型后全库重建——按配置页 rag.embeddingModel 逐条重嵌表内原文。
    零令牌（本机 Ollama）；维度不符 pgvector 会报错=让问题可见，绝不静默。
    R68 修 评审A P0/评审B🟡8/评审E二.2.4：逐条嵌入是分钟级同步活，旧版直跑 async 处理器=卡死整个
    事件循环（对话/健康检查全挂）——改 asyncio.to_thread 落线程池 + 重入锁 + finally 关连接。"""
    global _RAG_REBUILDING
    if _RAG_REBUILDING:
        return {"error": "重建正在进行中，请等完成再触发（防并发互踩）"}
    from settings_mgr import load_settings, DEFAULT_EMBED_MODEL
    model = (load_settings().get("rag", {}) or {}).get("embeddingModel", "") or DEFAULT_EMBED_MODEL

    def _sync():
        conn = _rag_pg()
        if not conn:
            return {"error": "PG 不可用，重建中止（先查 postgres 容器）"}
        n = 0
        try:
            import httpx
            with conn.cursor() as cur:
                cur.execute("select id, text from rag_chunks")
                rows = cur.fetchall()
                for cid, text in rows:
                    r = httpx.post("http://host.docker.internal:11434/api/embed",
                                   json={"model": model, "input": (text or "")[:4000]}, timeout=60)
                    vec = r.json()["embeddings"][0]
                    cur.execute("update rag_chunks set vec=%s::vector where id=%s", (str(vec), cid))
                    n += 1
            conn.commit()
            return {"ok": True, "model": model, "updated": n}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    _RAG_REBUILDING = True
    try:
        return await asyncio.to_thread(_sync)
    finally:
        _RAG_REBUILDING = False
