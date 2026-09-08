#!/bin/bash
# m-health.sh — M 平台一键体检（容器/端点/真错误）
# 用法: m-health.sh
echo "── 容器 ──"
docker ps --format '{{.Names}}  {{.Status}}' | grep -E "workplatform|sandbox|postgres|redis|searxng|n8n"
echo "── 端点 ──"
printf "office2024: %s  " "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:2024/health --max-time 5)"
printf "dev3000: %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000 --max-time 10)"
WP=$(docker ps --filter "name=workplatform" --format "{{.Names}}" | head -1)
echo "── 近30分钟真实错误（已滤 structlog 的 error_detail=None 假阳性）──"
N=$(docker logs "$WP" --since 30m 2>&1 | grep -E "Traceback|Exception in ASGI|NameError|SyntaxError" | grep -vc "error_detail")
echo "真实错误行数: $N"
[ "$N" != "0" ] && docker logs "$WP" --since 30m 2>&1 | grep -E "Traceback|Exception in ASGI" | head -3
