"""mcal 助手持久记忆 —— checkpoint 层（对话历史/线程状态）

放在 D:/m/workspace/checkpointer.py（与 langgraph.json 同级）
表建在 m 库（checkpoint_* 系列表），幂等：重复运行不重复建表
连接串读取顺序：M_DB_URI（老规矩）→ DATABASE_URI（compose 官方名）
"""

import os
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def make_checkpointer():
    """langgraph.json 里 checkpointer.path 指到这里。

    langgraph dev 启动时调用：建连接 → setup() 建表 → 交出 saver
    """
    db_uri = os.environ.get("M_DB_URI", "") or os.environ.get("DATABASE_URI", "")
    if not db_uri:
        raise RuntimeError(
            "数据库连接串未设置。请在 D:\\m\\workspace\\.env 里加 M_DB_URI，"
            "或 compose 里给 DATABASE_URI（postgresql://postgres:密码@postgres:5432/m）"
        )
    async with AsyncPostgresSaver.from_conn_string(db_uri) as saver:
        await saver.setup()  # 首次运行建表，之后是空操作
        yield saver
