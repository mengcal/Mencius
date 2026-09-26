# AgentDiary 门禁钩子（gate_hook）

宿主侧 **PreToolUse** 钩子：任何执行类动作前，本会话必须先读过日记，否则 **deny** 并记录拦截日志。

## 协议

- **输入**：stdin 接收 PreToolUse JSON
  `{"session_id": "...", "tool_name": "Bash", "tool_input": {"command": "..."}}`
- **输出**：stdout 返回 `permissionDecision`（`allow` / `deny`）+ 原因
- **防呆**：钩子自身崩溃 = 非阻塞错误，不锁死宿主

## 判定规则（按顺序）

1. **GATE-OFF 急停**：数据根下存在 `GATE-OFF` 空文件 → 全放行
2. **只读白名单**：Bash 命令为只读安全姿势 → 放行（防死锁，读日记活路永远敞开）
   - 安全命令：`ls cat head tail wc grep rg fd find date echo pwd which stat du df cd`
   - `sed`：仅带 `-n` 且不带 `-i` 放行（`sed -i` 是写文件，拦）
   - `git`：仅 `status/log/diff/show/branch` 放行
   - `python[3] …diary.py read …`：读日记姿势放行；其余 python 一律视为执行类
   - 复合命令（`&& || ; |`）**按段判定**：每段都安全才放行，任一段危险即 deny
   - 前导环境变量赋值（`FOO=bar …`）自动跳过；引号/绝对路径经 shlex 分词不误拦
3. **已读放行**：本会话在 DiaryStore 中已 `has_read_diary` → 放行
4. **否则 deny**：提示先读日记，并 `log_block` 落库

## 安装（ZCode 宿主）

1. 本文件随 agent-diary 仓分发；宿主将 `gate_hook.py` 复制/链接到宿主 hooks 目录，
   并在 hook 配置中注册为 PreToolUse（命令：`python <此文件路径>`）。
2. 环境变量（可选）：
   - `GATE_DIARY_ROOT`：日记数据根（默认 `~/.agent-diary/live`）
   - `GATE_DIARY_PKG`：agent_diary 包所在目录（默认按本文件位置自动推导：`<hooks>/..`，即本仓根）
3. 急停：在 `GATE_DIARY_ROOT` 下新建空文件 `GATE-OFF` 即全放行（删掉恢复门禁）。

## 回归

`hooks/test_gate_hook.py` 九例对照（退出码 0 = 全过）：

1. 未读日记：写类命令（`rm`、`git push`）→ deny
2. 读日记活路：`python diary.py read` → allow
3. sed 判定：`sed -n` 只读 allow / `sed -i` 写入 deny
4. 复合命令按段：危险段 deny / 全只读 allow
5. 引号路径：`python "/目录带空格/diary.py" read` 不误拦
6. 前导 env 赋值：`FOO=bar python3 diary.py read` 放行
7. git 安全子命令：`git status/log` allow
8. 已读日记后：写类命令 allow
9. GATE-OFF 急停：全放行

```bash
python hooks/test_gate_hook.py
```

## 版本

- **v1.2（09-25 纳仓版）**：路径参数化（`GATE_DIARY_ROOT` / `GATE_DIARY_PKG`，默认自动推导），
  去除个人机器路径；保留 v1.1 全部修复（shlex 分词、复合命令分段、前导 env 跳过、
  `sed -n`/`-i` 判定、git 安全子命令）；新增 GATE-OFF 急停开关。
