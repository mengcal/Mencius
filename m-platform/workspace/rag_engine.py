"""R69（评审E🟡4 双实现合并）：pgvector 检索的唯一实现——
agent 工具 search_knowledge_base 与 office /rag/query 共吃这一份 SQL，改一漏一的历史结束。
失败必出声（raise），由调用方决定兜底（office 回 JSON / 工具回错误文本）。"""
import os


def search_vectors(qvec, k=5):
    """按余弦距离取 top-k，返回 [(name, text, score)]。"""
    import psycopg2
    uri = os.environ.get("DATABASE_URI") or ""
    if not uri:
        raise RuntimeError("DATABASE_URI 未设置（宁报错不弱口令，R69）")
    conn = psycopg2.connect(uri, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select name, text, 1 - (vec <=> %s::vector) as score from rag_chunks "
                "order by vec <=> %s::vector limit %s",
                (str(qvec), str(qvec), max(1, min(int(k), 50))))
            return cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass
