# Recall 🔍 — 给智能体的"微信式"按需召回

**一个 160 行的零依赖 CLI：让 AI 编程助手自己搜回历史对话，而不是你替它粘贴。**

> "我上个月跟它说过这个坑，这周它又踩了一遍。"
> —— 每个用 AI 编程超过一个月的人的痛。

## 这是什么

AI 编程工具的会话记录是**一次性上下文**：会话一结束（或被压缩），细节就没了。
市面已有一批"聊天记录查看器"（claude-code-history-viewer、Lovcode、Claude 官方聊天搜索等）——
但它们都是**给人看的 GUI/云端服务**。智能体自己用不上：它不能"打开一个桌面应用"。

Recall 反过来设计：**给 agent 调用的命令行工具**。
你在任何会话里说一句"查查咱们以前怎么处理 X 的"，模型就跑：

```bash
python recall.py X 处理
```

多关键词 = 同一行同时包含（**微信搜聊天记录的 AND 手感**），
结果按日期分组倒序、每条带 `文件:行号` 出处，模型可以直接 Read 那一行附近取证。

## 它搜什么

**不解析任何厂商私有格式。** 只搜你导出/落盘的纯文本档案——
所以它对 Claude Code / Codex / ZCode / Qoder / CodeBuddy 的导出物一视同仁：
会话导出（markdown/jsonl 均可）、工程日志、日记、信箱归档…… 都是普通文本文件。

数据源写在 `recall-sources.txt`（每行一条，`标签=路径或glob`）：

```
对话全量=exports/conversations.md
工程账本=notes/eng-log.md
日记=notes/diary/*.md
```

## 用法

```bash
python recall.py 网关 超时              # 多词 AND
python recall.py 密钥 --days 30         # 只看最近 30 天
python recall.py --sources my.txt foo   # 指定数据源配置
```

### 接进你的智能体（关键一步）

把这条写进你的 AGENTS.md / CLAUDE.md / 系统提示：

> 遇到"以前/上次/之前怎么做的"类问题，先跑 `python recall.py <关键词...>` 再回答；
> 引用结果必须带出处行号；搜不到就明说搜不到，不许编。

配套 `SKILL.md` 可直接作为 ZCode / Claude Code 技能装载。

## 设计口径（为什么这么简单）

- **零依赖**：纯标准库，任何有 Python 3 的机器直接跑，装进沙箱容器也不用装包。
- **grep 哲学**：AND 同行匹配、大小写不敏感，宁可漏召回不可假命中——语义搜索（向量/RAG）是另一条路，
  但那条路要 embedding、要索引、要信任；档案在增长、模型在换、信任要钱。
  文本 + 正则 + 行号，**可审计性 100%**。
- **日期四级提取**：行内 `YYYY-MM-DD` → 标题行继承 → 文件名日期 → 文件 mtime，历史档案常见格式全覆盖。
- **编码宽容**：配置与档案 UTF-8 / UTF-8-BOM / Windows 记事本 ANSI(GBK) 都能读——中文用户第一。
- **家规友好**：支持 `--days` 时间窗与 glob 白名单，敏感目录不进配置就是不存在。

## 与同类工具的关系

| 工具 | 形态 | 谁在用 |
|---|---|---|
| claude-code-history-viewer / Lovcode | 桌面 GUI 查看器 | 人 |
| Claude 聊天搜索（官方） | 面向人的云端搜索（可用性/计费以官方方案为准） | 人+云端模型 |
| sync-transcript | hooks 自动存档 | 解决"存"，不解决"搜回" |
| **recall** | **零依赖 CLI，agent 自调** | **模型自己** |

互补不冲突：存档工具负责"留下"，recall 负责"想起来"。

## 许可

MIT © 2026 Mencius
