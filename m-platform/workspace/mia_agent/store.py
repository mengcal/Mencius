# -*- coding: utf-8 -*-
"""mia_agent/store.py —— mia_config reducer + MiaState + 官方 PG store
拆分来源：D:\\m\\workspace\\agent_multimodel.py 原 L165-168（_merge_mia）、
L804-806（MiaState）、L819-854（_STORE_CM / _make_store / _STORE）（拆分方案 #4）。
（原 L808-816 的 BASE/MEMORY_FILE 段不在此：BASE 按方案在 mia_agent/graph.py 定义，
 MEMORY_FILE 建档副作用随之归 graph.py，
依赖：deepagents.graph.DeepAgentState、typing、typing_extensions；
langgraph.store.postgres 在 _make_store 内懒加载（与原实现一致）。
被引用：mia_agent/tools.py（edit_memory 的 PG 镜像写 _STORE，原 L544）、
mia_agent/graph.py（store=_STORE，原 L1019；state_schema=MiaState，原 L1027）。
"""
from typing import Annotated  # 原 L121
from typing_extensions import NotRequired  # 原 L122
from deepagents.graph import DeepAgentState  # 原 L120


def _merge_mia(a: dict | None, b: dict | None) -> dict:  # 原 L165-168
    """mia_config 并发合并（官方 reducer 模式）：多路同写时按键合并，不再报
    Can receive only one value per step（2026-08-30 管理员实测踩坑）。"""
    return {**(a or {}), **(b or {})}


class MiaState(DeepAgentState):  # 原 L804-806
    """自定义 state 通道：对话输入框的运行级配置（选的模型/联网开关）随消息传入"""
    mia_config: NotRequired[Annotated[dict, _merge_mia]]


# ── 官方 store 层（R63）：跨线程/跨会话永久记忆，PG 落库，与 langgraph API 服务端同源 ──（原 L819-824）
# 挂到 create_deep_agent(store=...)，助手的记忆从此走官方 BaseStore（namespace/key/value），
# 不再是纯文件自研；checkpointer 管对话历史（线程级），store 管全局共享事实（跨线程永久）。
_STORE_CM = None  # R68：上下文管理器本体必须模块级持引用——只留 store 的话 cm 出函数即被 GC，
                  # 连接当场关闭（R64 以为"__enter__ 持有"修好了，实际镜像从此全在 closed connection 上失败、
                  # 又被裸 except 吞了四十个小时，直到本次改"失败必出声"才现形。静默失败=最贵的失败。）


def _make_store():  # 原 L827-851
    import os as _os
    from langgraph.store.postgres import PostgresStore

    db_uri = (
        _os.environ.get("DATABASE_URI")
        or _os.environ.get("M_DB_URI")
        or ""  # R69：删 postgres:postgres 弱口令兜底（评审四.1.1）——宁报错不越权
    )
    if not db_uri:
        print("[mcal] DATABASE_URI/M_DB_URI 均未设置，PG store 不挂载（宁报错不弱口令）", flush=True)
        return None
    try:
        # from_conn_string 返回上下文管理器——进入并保持打开（进程生命周期），
        # 直接 .setup() 会报 '_GeneratorContextManager' has no attribute 'setup'（R63 隐藏 bug）
        cm = PostgresStore.from_conn_string(db_uri)
        store = cm.__enter__()
        store.setup()  # 首次建表，之后空操作
        global _STORE_CM
        _STORE_CM = cm  # R68：攥住 cm，防 GC 关连接
        print("[mcal] PG store 就绪（同步 PostgresStore，edit_memory 镜像走它）", flush=True)
        return store
    except Exception as e:  # store 挂了不影响 agent 启动（记忆回退文件层）
        print(f"[mcal] PG store 初始化失败，回退无 store：{e}", flush=True)
        return None


_STORE = _make_store()  # 原 L854
