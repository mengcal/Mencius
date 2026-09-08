NOTICE
====
M 平台 (m-platform) 基于或衍生自以下第三方项目，LICENSE 归属其各自作者：

- langchain-ai/deep-agents-ui — MIT License, Copyright (c) LangChain, Inc.
  （前端底座 deep-agents-ui/ 由此深度魔改）
- langchain-ai/deepagents — MIT License, Copyright (c) LangChain, Inc.
  （智能体运行时，经 pip 依赖引入）
- LangGraph / langgraph-api — MIT License, Copyright (c) LangChain, Inc.
  （后端容器基座镜像 langchain/langgraph-api）
- open-webui (ocapala/open-webui 等社区版) — BSD-3-Clause License
  （部分设置页交互/样式设计参考其公开实现，未复制源码；详见各文件注释的"参考"标注）

- Dify / LobeChat 等 — 个别管理交互（服务商单条保存等）参考其公开设计，未复制源码

- 其余第三方依赖见 deep-agents-ui/package-lock.json 与后端容器的包清单，
  各自遵循其原始许可证。

本仓库自身代码（未在上述归属列表中的部分）遵循 MIT License。
