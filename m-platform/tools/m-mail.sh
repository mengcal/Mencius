#!/bin/bash
# m-mail.sh — 知夏信箱查收（列最近邮件索引，全文用 python 按 UID 取）
# 用法: m-mail.sh [显示封数，默认12]
python /d/glm/projects/notes/_check_inbox.py 2>&1 | grep -E "^\[[0-9]+\]|主题:|日期:" | head -40
