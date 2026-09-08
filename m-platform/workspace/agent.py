"""官方 langgraph.json 的图入口（deep-agents-ui 对接用）。

langgraph.json 里 graphs 指向 ./agent.py:agent，
本文件只做转发：agent_multimodel 里 create_deep_agent 编译好的图直接交出去。
不改 agent_multimodel，零手搓，官方 langgraph dev 直接加载。
"""
from agent_multimodel import agent  # noqa: F401
