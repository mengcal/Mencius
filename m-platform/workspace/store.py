"""mcal store 层（简化版，无 langmem）

langgraph.json 的 store.path 指到这里。
只做一件事：建 AsyncPostgresStore（PG m 库）。
agent 的永久记忆走 FilesystemBackend 落盘 mia_home/memories/，不经过这个 store。
这个 store 留给 langgraph API 自身用（线程元数据等），无害。
读取顺序：DATABASE_URI（compose 容器内）→ M_DB_URI（老 .env，本地调试遗留兼容）
"""
import os
from contextlib import asynccontextmanager

from langgraph.store.postgres.aio import AsyncPostgresStore


@asynccontextmanager
async def make_store():
    db_uri = os.environ.get("DATABASE_URI", "") or os.environ.get("M_DB_URI", "")
    if not db_uri:
        raise RuntimeError("缺少 DATABASE_URI（compose）或 M_DB_URI（本地）")
    async with AsyncPostgresStore.from_conn_string(db_uri) as store:
        await store.setup()  # 首次建表，之后空操作
        print("[mcal] store 已就绪（PG m）")
        yield store
