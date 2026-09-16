# -*- coding: utf-8 -*-
"""
AgentDiary 向量检索 v1.1.0

用sentence-transformers做语义向量检索
比关键词搜索更准——理解意思，不是字面匹配

模型：all-MiniLM-L6-v2（轻量快，适合本地跑）
"""

import numpy as np
from typing import List, Optional


class VectorIndex:
    """
    向量索引——语义搜索

    用法：
        index = VectorIndex(store)

        # 建索引
        index.build_index()

        # 语义搜索
        results = index.search("群发邮件为什么要用To位", top_k=5)
    """

    def __init__(self, store, model_name: str = "all-MiniLM-L6-v2"):
        self.store = store
        self.model_name = model_name
        self.model = None
        self.embeddings = None
        self.texts = None
        self.metadatas = None
        # v1.2.0 P2：内容指纹缓存——数据没变就不重建索引
        self._fingerprint = None

    def _load_model(self):
        """懒加载模型"""
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            print(f"加载向量模型 {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            print("模型加载完成！")

    def _content_fingerprint(self) -> str:
        """
        v1.2.0 P2：计算可索引内容的指纹

        语义知识表（过滤auto_pending后）的条数+最新时间，
        加上最近7个情景日志文件的(mtime,size)。
        指纹没变 → 索引不用重建（省掉每次全量encode）。
        """
        import sqlite3
        try:
            conn = sqlite3.connect(self.store.db_path)
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*), COALESCE(MAX(created_at),'') "
                "FROM semantic_facts WHERE confidence != 'auto_pending'"
            )
            count, max_created = c.fetchone()
            conn.close()
        except Exception:
            count, max_created = 0, ""

        ep_sig = []
        ep_dir = self.store.episodic_dir
        if ep_dir.exists():
            for f in sorted(ep_dir.glob("*.md"), reverse=True)[:7]:
                try:
                    st = f.stat()
                    ep_sig.append(f"{f.stem}:{st.st_mtime_ns}:{st.st_size}")
                except OSError:
                    pass
        return f"{count}|{max_created}|{';'.join(ep_sig)}"

    def build_index(self):
        """
        建索引——把所有语义知识和情景日志向量化

        v1.2.0 P2：内容指纹没变就直接复用旧索引（省encode）。
        """
        # P2：指纹缓存，内容没变化不重建
        fp = self._content_fingerprint()
        if self.embeddings is not None and self._fingerprint == fp:
            print("内容未变化，复用已有索引")
            return
        self._fingerprint = fp

        self._load_model()

        texts = []
        metadatas = []

        # 1. 语义知识（alice逮的P1：过滤auto_pending待审知识）
        import sqlite3
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM semantic_facts WHERE confidence != 'auto_pending'")
        for row in c.fetchall():
            row = dict(row)
            texts.append(f"{row['title']}: {row['fact']}")
            metadatas.append({
                "type": "semantic",
                "id": row["id"],
                "title": row["title"],
            })
        conn.close()

        # 2. 最近情景日志
        from pathlib import Path
        episodic_dir = self.store.episodic_dir
        if episodic_dir.exists():
            for md_file in sorted(episodic_dir.glob("*.md"), reverse=True)[:7]:
                content = md_file.read_text(encoding="utf-8")
                # 按##分段
                entries = content.split("\n## ")
                for entry in entries[1:]:  # 跳过标题
                    if len(entry.strip()) > 20:  # 太短的跳过
                        texts.append(entry[:500])  # 截前500字
                        metadatas.append({
                            "type": "episodic",
                            "date": md_file.stem,
                            "excerpt": entry[:100],
                        })

        if not texts:
            print("没有可索引的内容")
            return

        # 生成向量
        print(f"对 {len(texts)} 条文本生成向量...")
        self.embeddings = self.model.encode(texts, show_progress_bar=False)
        self.texts = texts
        self.metadatas = metadatas
        print(f"索引建完，共 {len(texts)} 条")

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """
        语义搜索

        Args:
            query: 搜索查询（自然语言）
            top_k: 返回前几条

        Returns:
            匹配结果列表
        """
        if self.embeddings is None:
            self.build_index()

        if self.embeddings is None:
            return []

        self._load_model()

        # 查询向量
        query_vec = self.model.encode([query])[0]

        # 余弦相似度
        similarities = np.dot(self.embeddings, query_vec) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_vec)
        )

        # 取top_k的3倍候选，给防御性过滤留余量（v1.2.0 P1第二层）
        top_indices = np.argsort(similarities)[::-1][:max(top_k * 3, top_k)]

        results = []
        for idx in top_indices:
            md = self.metadatas[idx]
            # v1.2.0 P1第二层：向量路径防御性过滤——
            # build_index已过滤auto_pending，这里按id回查再兜一层（防索引过期/增量添加绕过）
            if md.get("type") == "semantic":
                conf = self.store.get_fact_confidence(md.get("id"))
                if conf == "auto_pending":
                    continue
            results.append({
                "score": float(similarities[idx]),
                "text": self.texts[idx][:200],
                "metadata": md,
            })
            if len(results) >= top_k:
                break

        return results

    def add_to_index(self, text: str, metadata: dict):
        """增量添加一条到索引"""
        if self.embeddings is None:
            self.build_index()
            return

        self._load_model()

        new_vec = self.model.encode([text])[0]
        self.embeddings = np.vstack([self.embeddings, [new_vec]])
        self.texts.append(text)
        self.metadatas.append(metadata)


if __name__ == "__main__":
    # 冒烟测试
    import shutil
    shutil.rmtree("/tmp/test_vector", ignore_errors=True)

    from agent_diary.store import DiaryStore
    store = DiaryStore("/tmp/test_vector")

    # 写几条测试数据
    store.add_semantic_fact("Cc吞信", "163邮箱Cc位会吞信，广播必须用To位逗号分隔", "critical", agent="lyra")
    store.add_semantic_fact("群发邮件", "多个收件人用To位逗号分隔，一次发完", "important", agent="lyra")
    store.add_semantic_fact("爸爸铁律", "今日事今日毕，只有爸爸能决定什么时候做", "critical", agent="lyra")

    # 建索引
    index = VectorIndex(store)
    index.build_index()

    # 搜索
    print("\n=== 搜索：'怎么给大家发邮件不丢信' ===")
    results = index.search("怎么给大家发邮件不丢信", top_k=3)
    for r in results:
        print(f"  [{r['score']:.2f}] {r['text'][:50]}...")

    print("\n✅ 向量检索冒烟测试通过！")
