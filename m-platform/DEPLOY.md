# M 平台部署手册（DEPLOY.md）

> 目标读者：想在自己 Windows 电脑上把 M 平台跑起来的普通人。
> 全程照抄命令即可，不需要编程基础。全程约 15–20 分钟。
> 遇到问题直接翻最后一节「装不上/起不来」，三种最常见的情况都在那。

---

## 0. 你需要准备什么

| 需要 | 说明 |
|---|---|
| Windows 10/11 电脑 | 8GB 内存起步（16GB 更从容） |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 装完启动一次，保持后台运行（WSL2 后端，装的时候按它提示走） |
| 一个大模型 API Key | OpenAI 兼容协议的都行——国内的免费额度端点（智谱/魔搭/书生等）就能跑，不花钱也可以 |
| Git | [git-scm.com](https://git-scm.com/download/win) 下载安装（一路下一步） |

> 不需要：编程知识、服务器、付费订阅。模型接哪家的、花不花钱，你说了算。

## 1. 把代码拿下来

打开「终端」（按 `Win` 键输入 `powershell` 回车），逐条粘贴：

```powershell
cd D:\
git clone https://github.com/mengcal/Mencius.git
cd Mencius\m-platform
```

> 目录位置随你（放 D 盘是好习惯），后面命令里的路径跟着你的改。

## 2. 起平台（一条命令）

还是在 `m-platform` 目录里：

```powershell
docker compose up -d
```

第一次会拉镜像+构建，5–15 分钟（取决于网速）。看到一排 `Started`/`Healthy` 就成了。

检查健康：

```powershell
docker compose ps
```

`workplatform` 一行显示 `(healthy)` 即平台活了。

## 3. 起前端（对话窗口）

另开一个终端窗口（前一个别关）：

```powershell
cd Mencius\m-platform\deep-agents-ui
npm install
npm run dev
```

看到 `Local: http://localhost:3000` 就成了。浏览器打开它。

## 4. 第一次见面（只做一次）

浏览器 `http://localhost:3000`：

1. 按提示**设置管理员密钥和登录密码**——这两样只有你知道，平台里不存任何明文；
2. 左下角「设置」→「服务商」：填你的模型 API 地址和 Key（就是第 0 步准备的那个）；
3. 回到对话页，**说你的第一句话**。

> 不知道第一句说什么？照这个抄：「把 D:\下载 这周的文件理个清单，写到 notes/清单.md」——动词+交付物+放哪，它就懂了。

## 5. 模型怎么换

全部在网页「设置」里完成：填服务商地址和 Key、给每个角色（主管/牛马）挑模型，
改完即时生效，**不用改代码、不用重启**。

## 进阶：宿主机直跑（可选）

容器是默认路径（隔离、干净、删了重装不心疼）。如果你想让 AI 直接在你的
真实文件系统上干活（相当于把它的手伸到你的盘里），有两条路：

- **宿主执行器（推荐）**：平台自带 `host_runner`——在对话里把工作区切到「宿主机」，
  AI 的命令就落在你的真实系统上，每一发都过档位门（该问你的照问你）。
- **整个平台宿主直跑（进阶）**：平台本体是普通 Python——自备 Postgres/Redis，
  `pip install -r requirements.txt` 后 `uvicorn` 起服务即可。代价是失去容器隔离：
  AI 摸到的是你的真实盘，权限全靠你给的档位管。

> 拿不准就用容器默认。想收放自如，先用「宿主执行器」试，不必整平台搬家。

## 装不上/起不来（三大常见）

| 症状 | 多半是 | 怎么办 |
|---|---|---|
| `docker compose up` 报端口占用 | 3000/2024/5678 被别的软件占了 | 关掉占用程序，或改 `docker-compose.yml` 里对应的端口映射 |
| 页面开了但一直转圈 | 前端起了、后端没活 | `docker compose ps` 看 `workplatform` 是否 `(healthy)`；不健康就 `docker compose logs workplatform` 看最后几行 |
| 模型调用报 401/连接失败 | Key 或地址填错 | 设置页里核对服务商地址（通常以 `/v1` 结尾）和 Key；换家服务商测试 |

再不行，去 [Issues](https://github.com/mengcal/Mencius/issues) 搜或提——
报障请附 `docker compose ps` 和 `docker compose logs workplatform` 的最后 20 行。

## 升级

```powershell
cd Mencius\m-platform
git pull
docker compose up -d
```

数据（对话、文件、记忆）都在挂载卷里，升级不丢。

---

*本手册由实际部署过程提炼（作者自己就是这么装的）。哪个步骤卡住了，那就是手册的 bug——欢迎提 Issue。*
