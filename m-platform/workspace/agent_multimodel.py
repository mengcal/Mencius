# -*- coding: utf-8 -*-
"""（拆分后占位）原 D:\\m\\workspace\\agent_multimodel.py（1034 行）已整体拆入 mia_agent/ 包。
本文件 = 部署时替换原文件的转发桩：保留原模块名，供 langgraph.json / agent.py /
office/app.py / cow_graphs.py 继续以 `import agent_multimodel` / `from agent_multimodel import X` 引用。
部署方式：把 mia_agent/ 整个包目录放到工作区根（D:\\m\\workspace\\mia_agent\\），
再用本文件覆盖 D:\\m\\workspace\\agent_multimodel.py —— graph.BASE = 包目录上一级，
恰好指回工作区根（与拆分前 `Path(agent_multimodel.py).parent` 同值）。
兼容转发清单（依据全仓 grep agent_multimodel，2026-09-06）：
  agent.py:7、office/app.py:30   → agent
  cow_graphs.py:59 / 275         → SandboxedShellBackend
  cow_graphs.py:68 / 275         → ConfirmGateMiddleware、search_knowledge_base
（故除方案指定的 agent 一行外，另补三个兼容转发，防 cow_graphs 引用断裂；
"""
from mia_agent.graph import agent  # noqa: F401  （拆分方案指定的一行转发，全量实现已拆入 mia_agent/）
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: F401  （cow_graphs.py:68/275 兼容转发）
from mia_agent.sandbox import SandboxedShellBackend  # noqa: F401  （cow_graphs.py:59/275 兼容转发）
from mia_agent.tools import search_knowledge_base  # noqa: F401  （cow_graphs.py:68 兼容转发）
