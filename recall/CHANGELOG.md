# Changelog

## v1.0.0 (2026-09-22)
- 首发：零依赖单文件 CLI，多关键词同行 AND、日期分组倒序、`文件:行号` 出处。
- 数据源配置：`--sources` / `RECALL_SOURCES` / `./recall-sources.txt` / `~/.recall-sources.txt` 四级查找。
- `--days` 时间窗、`--max-hits` 上限；日期三级提取（行内 → 文件名 → mtime）。
- 设计源自"微信搜聊天记录"手感 + 智能体跨会话记忆缺失的工程实践（AgentDiary 同门）。
