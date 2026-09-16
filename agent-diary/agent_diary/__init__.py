# -*- coding: utf-8 -*-
"""
AgentDiary 📔

给智能体的工作日志系统——不是人类日记，是触发式记忆门禁

核心组件：
- DiaryStore: 存储层（情景日志/语义知识/程序手册）
- MemoryGate: 门禁中间件（不读不能动手、动完必记）
- make_diary_tools: 创建read_diary/write_diary工具
"""

from .store import DiaryStore
from .memory_gate import MemoryGate
from .tools import make_diary_tools

__version__ = "0.1.0"
__all__ = ["DiaryStore", "MemoryGate", "make_diary_tools"]
