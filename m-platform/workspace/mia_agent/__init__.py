r"""
助手「工作平台·后台任务队列」多模型引擎（可配置版）—— 拆分包
=====================================================================
（本 docstring 承接自原 D:\m\workspace\agent_multimodel.py 的模块 docstring，原 L1-9。
 拆分对照表）
管理员拍板定稿（2026-08-27）+ R65 清硬编码（2026-09-01）：
  ① 工人岗矩阵唯一真源 = 设置页 settings.agents（经 settings_mgr.load_agents_config 取，本模块不再自建 loader）
  ② 服务商 = 设置页 external 节（按名字查，名字对不上宁报错不越权）
  ③ 成本分层：平时便宜小模型，大活才临时升配（助手 set_model 升降配，省钱第一）
  ④ 此处不写死任何"哪个角色用哪家"——角色与模型全在设置页配置。

拆分后引用姿势：from mia_agent.graph import agent
（__init__ 刻意保持零副作用：不在此 import graph——import 本包即建全图的行为
 收敛到显式 import mia_agent.graph 一处，与原 monolith 语义一致。）
"""
