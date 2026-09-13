#!/bin/bash
# hy-probe.sh — CodeBuddy hy 免费额度探针（hy4/hy3 各一发，秒回=在，400/429=没了）
# 用法: hy-probe.sh
for m in hy4-preview hy3; do
  R=$(env -u CODEBUDDY_API_KEY -u CODEBUDDY_BASE_URL -u CODEBUDDY_MODEL \
      codebuddy --model "$m" -p "只回一个字：在" --max-turns 1 --tools "" 2>&1 | head -1)
  echo "$m: $R"
done
