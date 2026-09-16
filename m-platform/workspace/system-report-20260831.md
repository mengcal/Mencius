# 知夏系统环境报告（2026-08-31 22:00 生成）

> 底稿：腾讯电脑管家硬件信息 + ZCode 系统实测盘点
> 用途：开发环境基线存档 + 米娅协作参考

---

## 一、硬件概览

| 项 | 值 |
|---|---|
| CPU | Intel Core i9-9900K @ 3.60GHz 八核（52°C） |
| 主板 | 华硕 PRIME Z390-P（BIOS 3006, 2021-10-12） |
| 内存 | 32GB (2×16GB 海盗船 3200MHz) |
| 显卡 | NVIDIA GeForce RTX 2070 SUPER 8GB（驱动 616.56, CUDA 13.3） |
| 系统盘 | 三星 SSD 9100 PRO 1TB |
| 数据盘 | 东芝 MD08ADA600 6TB / 英特尔 SSD 256GB / ST 2TB |
| 显示器 | 飞利浦 322M7C 31.5" 1080p 60Hz |
| 网卡 | Realtek PCIe GbE |
| OS | Windows 11 家庭版 中文版 64-bit（安装日期 2026-07-11） |

**开发能力评估**：CPU 8核16线程 + 32GB 内存 + RTX 2070S 8GB，本地跑 LM Studio / Ollama 中等模型够用，大模型训练吃紧（8GB 显存瓶颈）。CUDA 13.3 已装，NVIDIA Nsight 2026.2 性能分析工具齐备。

---

## 二、包管理器

| 工具 | 路径 | 版本/备注 |
|---|---|---|
| Node.js | /c/nodejs | v24.16.0 |
| npm | /c/nodejs/npm | 随 Node |
| npx | /c/nodejs/npx | 随 Node |
| yarn | /c/nodejs/yarn | 随 Node |
| pnpm | /c/nodejs/pnpm | 随 Node |
| pip | pyenv shim | 多版本管理 |
| pyenv-win | /c/Users/wolfm/.pyenv/pyenv-win | 管理 4 个 Python 版本 |
| go | /c/Program Files/Go/bin/go | go1.26.5 |
| dotnet | /c/Program Files/dotnet/dotnet | SDK 10.0.302 |

**npm 全局包**（D:\AI\npm-global）：
- @clawemail/mail-cli@0.2.4（米娅邮件 CLI）
- @tencent-qqmail/agently-cli@1.0.17（腾讯 AI Agent CLI）

**pyenv Python 版本**：3.10.6(默认) / 3.11.9 / 3.12.0 / 3.14.3 —— 全局 pip 包 267 个

---

## 三、开发运行时

| 运行时 | 版本 | 状态 |
|---|---|---|
| Python (pyenv 默认) | 3.10.6 | 活跃 |
| Python 3.12.0 | 已安装 | PyCharm 2026.1.4 使用 |
| Python 3.14.3 | 已安装 | 最新版 |
| Node.js | 24.16.0 | 活跃 |
| Go | 1.26.5 | 活跃 |
| .NET | SDK 10.0.302 | 活跃（含 Android/MAUI 开发） |
| CUDA | 13.3 | 活跃（Nsight 2026.2） |
| WSL | 2.9.4.0 | Ubuntu 已安装 |

---

## 四、容器与编排

| 工具 | 版本 | 状态 |
|---|---|---|
| Docker Desktop | 4.88.1 | 活跃，Docker Engine 29.7.2 |
| Docker Compose | 随 Desktop | M 平台 5 服务 compose (workplatform/postgres/redis/n8n/sandbox/searxng) |
| WSL | 2.9.4.0 | Ubuntu 后端可用 |

---

## 五、数据库

| 数据库 | 版本 | 状态 |
|---|---|---|
| PostgreSQL | 16.4-1 | 安装中（M 平台 m-postgres 容器也在跑） |
| SQL Server LocalDB | 17.0.4025.3 | 已安装 |
| Redis | — | M 平台 m-redis 容器 |

---

## 六、IDE 与编辑器

| IDE | 版本 | 备注 |
|---|---|---|
| PyCharm | 2026.1.4 | Python 主力 IDE |
| VS Code | — | 装有以下扩展：Python、Pylance、DebugPy、语言包(简/繁中文)、Containers |
| Visual Studio | — | VS Installer 4.8.60，含 .NET/Android/MAUI 开发 workload |
| LM Studio | 0.4.15+2 | 本地模型推理 |

---

## 七、开发工具链

| 工具 | 路径/备注 |
|---|---|
| Git | 2.55.0.5（C:\Git，ZCode 命令环境） |
| 7-Zip | 26.02 |
| WinRAR | 7.23 |
| WinMerge | 2.16.58（文件对比） |
| Everything | 1.4.1.1032（文件搜索） |
| WinDirStat | 2.7.0（磁盘可视化） |
| CrystalDiskInfo | 9.9.2（硬盘健康） |
| Core Temp | 1.20.1 |
| CPU-Z | 2.21 |
| KeePassXC | 2.7.12（密码管理） |
| Cryptomator | 1.19.3（文件加密） |
| Joplin | 3.7.12（笔记） |
| Obsidian | 1.12.7（知识库） |
| 有道云笔记 | 8.2.81 |
| 坚果云 | 7.2.12（同步） |

---

## 八、网络与下载

| 工具 | 状态 |
|---|---|
| 迅雷 | 25.0.90.1592 |
| 夸克 PC 版 | 7.1.5.968 |
| UC 浏览器 | 1.1.0.22 |
| curl | Git Bash 内置 |
| wget | Git Bash 内置 |
| searxng | 本地 18080 端口（M 平台部署） |

---

## 九、AI 与 ML 工具

| 工具 | 状态 |
|---|---|
| LM Studio | 本地推理（RTX 2070S 8GB） |
| CUDA 13.3 + Nsight 2026.2 | GPU 开发/分析 |
| PyCharm + 267 pip 包 | Python AI 开发 |
| ZCode + 插件生态 | AI 辅助编程 |
| M 平台 (langgraph/deepagents) | Agent 编排 |

---

## 十、M 平台依赖环境

| 组件 | 位置 | 状态 |
|---|---|---|
| workspace (Docker) | D:\m/workspace | 活跃 |
| deep-agents-ui (Next.js) | D:\m/deep-agents-ui | 3000 端口运行 |
| office.py (FastAPI) | D:\m/workspace | 2024 端口 |
| agent_multimodel.py | D:\m/workspace | 米娅主 agent |
| departments_config.json | D:\m/workspace | 3 部门配置 |
| cow_graphs.py | D:\m/workspace | 部门图构建 |
| settings_mgr.py | D:\m/workspace | 设置管理 |
| run_config.py | D:\m/workspace | RunConfig 中间件 |
| PostgreSQL | m-postgres 容器 | RAG pgvector |
| Redis | m-redis 容器 | 会话缓存 |
| n8n | m-n8n 容器 | 15678 端口（工作流自动化） |
| sandbox | m-sandbox 容器 | 代码沙箱 |
| searxng | m-searxng 容器 | 18080 端口（元搜索） |

---

## 十一、安全与凭证

| 项 | 位置 | 备注 |
|---|---|---|
| 知夏邮箱 | D:\glm\projects\notes\secrets\celia_mailbox.md | mencius.celia@claw.163.com |
| 米娅密钥 | archive/MEMORY.md | mkcalm.mia@claw.163.com |
| ZCode 配置 | C:\Users\wolfm\.zcode\cli\config.json | 20 启用插件 |
| M 平台 settings | D:\m/workspace/settings.json | 密钥在 secrets 节 |

**安全约束**：Mimosa 安全扫描启用中；源码不写凭据字面量；HTTP 请求校验 host（拒绝 localhost/私有地址——但 M 平台内网通信例外）。

---

## 十二、待办/缺失项

- [ ] Tavily CLI 未安装（Web 搜索受限，searxng 替代）
- [ ] 米娅无邮件收发工具（IMAP/SMTP 未接入，A2A 心跳循环缺环）
- [ ] MCP 服务器未配置（settings.json mcp.servers 为空）
- [ ] C:\Program Files\Git 残骸待管理员删除（5.7MB，2 个文件 ACL 锁死）
- [ ] 旧对话的汇报折叠不生效（只对折叠后新消息生效）

---

*报告生成时间：2026-08-31 22:00 | 知夏 (Celia) 存档*