# M 平台（助手工作平台）

> 本目录是 [Mencius](../README.md) 仓库中的独立项目：单机自托管 AI 工作平台。

单机自托管的 AI 工作平台：一位主理智能体（助手）带着一支军事化编制的智能体团队，
在完全跑在自己电脑上的 Docker 栈里干活——聊天、调研、写代码、跑脚本、管知识库、收发邮件、定时任务。

> 这是「个人自用优先」的项目：部署目标是**一台你信得过的 Windows 机器**，不是公网服务。
> 安全设计的出发点：防平台内的智能体越权、防宿主上的其他进程摸密钥。信任边界=你（机器管理员）本人+平台守卫；不防"已经拿到你 Windows 管理员权限的人"（那是操作系统的地盘）。

## 架构一图流

```
┌─ Windows 宿主 ──────────────────────────────────────────────┐
│  浏览器 localhost:3000 (Next.js 前端, deep-agents-ui 魔改)     │
│      │  同源 /lg 代理(rewrites→2024, Cookie HttpOnly)         │
│  ┌───▼──────────────┐   m-guard 守卫服务(127.0.0.1:9101)     │
│  │ workplatform:8000 │←── DPAPI 加密 token.bin/password.bin  │
│  │ FastAPI+langgraph │    管理密钥/密码 只存宿主加密存储        │
│  │  office/  = 网关层 │    (写端点 401 门 / 限频 / 64KB 体帽)   │
│  │  mia_agent/ = 引擎 │                                      │
│  └───┬──────┬───────┘                                        │
│  postgres   redis     n8n      searxng    sandbox           │
│  (pgvector  (缓存/   (自动化)  (元搜索)   (execute 沙箱)      │
│   RAG+记忆)  队列)                                          │
└─────────────────────────────────────────────────────────────┘
```

## 核心特性

- **军事化智能体编制**：助手（主理）→ 调度 → 部门组长 → 工人岗，逐级派活/汇报。
  编制唯一真源在设置页 `settings.agents`，改配置即生效，不用改代码。
- **四档确认门**（对标主流编码智能体的权限档）：`plan` 只读 / `strict` 变更前请示 /
  `auto_edit` 墙内写放行 / `full` 完全访问。危险工具（执行/删除/发信/派活）只认**外部批准**，
  且批准绑定**参数指纹**——批完换参数=重新拦截。模型自己反复重试不放行。
- **自锁守卫**：任何档位下，智能体的写工具都碰不了平台源码、档位文件、密钥路径。
- **密钥五级隔离**：Admin / WEBHOOK / SANDBOX / PROXY / GUARD 各自独立，桶不串。
- **m-guard 宿主守卫**：管理密钥与登录密码用 DPAPI（用户态）加密落盘 `token.bin` / `password.bin`，
  平台容器里没有任何明文；守卫带审计日志（三代轮转）、限频、防重放。
- **RAG 知识库**：pgvector 向量检索 + 重排，助手可 `search_knowledge_base` 直查。
- **技能锁**（skills_lock）：技能目录哈希基线，挂载回归即整体停用，宁可不带技能不裸奔。
- **后台任务队列**：`dispatch_background_task`（自研长任务派发，完成后自动回对话线程汇报；与 deepagents 内置 `start_async_task` 独立共存）；开关由 runner 注入，无独立设置项。

## 快速开始

前置：Windows 10/11、Docker Desktop、Node.js 20+、宿主 Python 3.12+（m-guard 用，默认经
pyenv-win 定位 `pythonw.exe`，也可设环境变量 GUARD_PYTHONW 指向你的 Python）。

> 路径约定：`docker-compose.yml` 以 `D:\m\`（平台）与 `D:\sandbox-workspace\`（沙箱草稿区）为部署示例路径——
> 换盘符/目录时全文替换即可，代码不依赖魔法位置。

```bash
# ⓪ 先建环境变量文件（缺它 compose 会拿空值起栈，守卫直接 403 死锁——这是自家踩过的坑）
#    Windows: copy .env.example .env  →  按文件内注释填好每一项

# ① 起后端六个容器（workplatform / sandbox / postgres / redis / n8n / searxng）
docker compose up -d

# ② 起前端（开发模式）
cd deep-agents-ui && npm install && npm run dev

# ③ 安装宿主守卫（管理员 PowerShell/cmd）
guard\install_system_task.cmd

# ④ 浏览器打开 http://localhost:3000
#    首次进入注册向导：设置管理员密钥 → 设置登录密码 → 完成

# ⑤ 部署自检（轻量、无需钥匙：容器状态+端口探活）
bash tools/m-health.sh
#    维护者深度门禁（需要本机真钥匙与内部路径，首次部署不必跑）：bash tools/m-gates.sh
```

模型接入：在设置页「服务商」里配你自己的 API Key（OpenAI 兼容协议均可），
Key 只经平台代理层转发给模型厂商，不进任何智能体的工具面。

> RAG 知识库的嵌入向量默认走本机 [Ollama](https://ollama.com)（qwen3-embedding，端口 11434）——
> 不启用 RAG 可完全忽略；启用请先拉起 Ollama 并拉取嵌入模型。

## 项目结构

```
workspace/            后端（跑在 workplatform 容器）
  office.py           转发桩（历史入口，实际实现在 office/）
  office/             FastAPI 网关层：core(纯函数) + app(装配) + routers/
    routers/gates.py      三扇代理门（识图/CodeBuddy/RAG）+ 体帽中间件
    routers/token_admin.py 管理密钥/密码/找回（no-rotate 登录）
    routers/tasks.py      后台任务与 webhook 汇报
    routers/providers.py  服务商管理
    routers/rag.py        知识库摄取/查询/重建
  agent_multimodel.py 转发桩（历史入口，实际实现在 mia_agent/）
  mia_agent/          助手引擎：graph(组图)/confirm_gate(确认门)/tools/
                      sandbox(沙箱后端)/store(永久记忆)/prompts
  cow_graphs.py       调度/部门/工人岗 各级图定义
  skills_lock.py      技能清单哈希锁
deep-agents-ui/       前端（基于 langchain-ai/deep-agents-ui 魔改，上游 MIT 归属见 NOTICE.md）
guard/                宿主守卫服务 + 安装/保活/重置脚本 + 109 条 unittest 断言
tools/                运维脚本：一键体检 m-health / 门禁回归 m-gates / 审计对账 m-audit-gates / 单测
skills/               技能目录（放入你的 .md 技能文件，compose 只读挂载）
searxng/              元搜索引擎配置
```

## 国内网络加速（可选，强烈建议）

本平台是"全家桶"，部署时要拉三类材料：Docker 镜像（六个容器）、npm 包（前端）、pip 包（后端）。
国内直连都慢，一次配好：

1. **Docker Hub 加速**：Docker Desktop → Settings → Docker Engine，加入
   `"registry-mirrors": ["https://docker.m.daocloud.io"]`
   （公共加速源时效性强，失效就换一个，或自备代理）。compose 要拉的
   langgraph-api / pgvector / redis / n8n / searxng 全走这里，省九成等待。
2. **npm 走 npmmirror**（淘宝源）：
   ```bash
   npm install --registry=https://registry.npmmirror.com
   ```
3. **pip/apt 不用操心**：`workspace/Dockerfile` 已内置清华 TUNA 镜像源，构建镜像时自动生效。

> 注：本 README 的"码云/Gitee"没有任何作用——Gitee 是代码托管不是软件源，
> 装东西快慢取决于上面三件事，不是 clone 地址。

## 安全模型

详见 [SECURITY.md](SECURITY.md)。要点：密钥 DPAPI 落盘不出宿主、五级密钥隔离、
同源代理 + HttpOnly Cookie、写端点 401 门 + 限频 + 请求体 64KB 上限、
批准绑定参数指纹、沙箱执行隔离、技能哈希锁、守卫审计日志。

## 致谢

- [langchain-ai/deep-agents-ui](https://github.com/langchain-ai/deep-agents-ui) —— 前端底座
- [deepagents](https://github.com/langchain-ai/deepagents) / LangGraph —— 智能体运行时

## License

[MIT](LICENSE) © 2026 zcode (Celia)
