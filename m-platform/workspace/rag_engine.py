"""R69（Qianwen🟡4 双实现合并）：pgvector 检索的唯一实现——
agent 工具 search_knowledge_base 与 office /rag/query 共吃这一份 SQL，改一漏一的历史结束。
失败必出声（raise），由调用方决定兜底（office 回 JSON / 工具回错误文本）。

r50（09-13，记忆升级 plan-memory 三信号）：排序=γ·relevance + β·importance + α·recency
  初值 α=0.2/β=0.3/γ=0.5（任务型；跑基线再调）；recency=exp(-age_days/30) 半衰期 30 天。
  向量预取 3k 候选再内存加权——pgvector 索引序≠三信号序，必须取宽池重排。
  老行 updated_ts 回填=入库时刻，importance 默认 0.5（迁移已做，幂等）。
"""
import os
import math
import time

# 三信号权重（plan-memory-upgrade-20260912 §三信号；任务型初值，跑基线再调）
W_RECENCY, W_IMPORTANCE, W_RELEVANCE = 0.2, 0.3, 0.5
HALF_LIFE_DAYS = 30.0
_CANDIDATE_POOL = 3000


def _recency(updated_ts):
    age_days = max(0.0, (time.time() - float(updated_ts or 0)) / 86400.0)
    return math.exp(-age_days / HALF_LIFE_DAYS)


def search_vectors(qvec, k=5):
    """三信号加权检索，返回 [(name, text, final, score, importance, recency)]。
    final = γ·relevance + β·importance + α·recency（检索结果按 final 降序）。"""
    import psycopg2
    uri = os.environ.get("DATABASE_URI") or ""
    if not uri:
        raise RuntimeError("DATABASE_URI 未设置（宁报错不弱口令，R69）")
    conn = psycopg2.connect(uri, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select name, text, 1 - (vec <=> %s::vector) as score, "
                "coalesce(importance, 0.5), coalesce(updated_ts, extract(epoch from now())) "
                "from rag_chunks order by vec <=> %s::vector limit %s",
                (str(qvec), str(qvec), _CANDIDATE_POOL))
            rows = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    scored = []
    for name, text, rel, imp, uts in rows:
        rec = _recency(uts)
        final = W_RELEVANCE * float(rel) + W_IMPORTANCE * float(imp) + W_RECENCY * rec
        scored.append((name, text, final, float(rel), float(imp), rec))
    scored.sort(key=lambda r: -r[2])
    return [(n, t, f, s, i, r) for n, t, f, s, i, r in scored[:max(1, min(int(k), 50))]]
