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

    def _load_model(self):
        """懒加载模型"""
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            print(f"加载向量模型 {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            print("模型加载完成！")

    def build_index(self):
        """
        建索引——把所有语义知识和情景日志向量化
        """
        self._load_model()

        texts = []
        metadatas = []

        # 1. 语义知识
        import sqlite3
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM semantic_facts")
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

        # 取top_k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                "score": float(similarities[idx]),
                "text": self.texts[idx][:200],
                "metadata": self.metadatas[idx],
            })

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
