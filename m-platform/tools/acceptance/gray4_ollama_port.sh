#!/usr/bin/env bash
# =============================================================================
# 灰区 #4 —— ragClient.ts OLLAMA_PORT = 11434
# 定性: 有意设计（注释声明"两个网络语境，各自单源": 浏览器直连本机 Ollama
#       vs 后端容器 MIA_OLLAMA_URL env）
# 依据: D:/m/docs/acceptance-checklist-v1.md 0.5 表 #4（台账组④）
# 验收口径: 有意声明在位 + 常量/字面量单源不扩散 + 消费活跃 + 后端对偶在位。
#           全机械可判: 命中数 / 行号差 / 文件集合全等 / 计数下界。
# 退出码: 0 = 全部通过; 1 = 任一失败
# 产出: CB glm-5.3（烧分战役⑦，09-22）；落盘/跑验: 知夏
# =============================================================================
set -u
SRC="D:/m/deep-agents-ui/src"
RC="D:/m/deep-agents-ui/src/lib/ragClient.ts"
rc=0

chk() {
  if [ "$2" = "$3" ]; then printf 'PASS %s expected=%s actual=%s\n' "$1" "$2" "$3"
  else printf 'FAIL %s expected=%s actual=%s\n' "$1" "$2" "$3"; rc=1; fi
}

# C1 定义唯一: 常量定义恰 1 处
chk "C1-def-unique" 1 "$(grep -cF 'const OLLAMA_PORT = 11434;' "$RC")"

# C2 有意声明紧邻: 声明行号 == 定义行号 - 1（当前 18/19）
d_line=$(grep -nF 'const OLLAMA_PORT = 11434;' "$RC" | head -1 | cut -d: -f1)
c_line=$(grep -nF '两个网络语境，各自单源' "$RC" | head -1 | cut -d: -f1)
chk "C2-intent-adjacent" "$(( ${d_line:-0} - 1 ))" "${c_line:-0}"

# C3 常量不扩散: OLLAMA_PORT 全 src 恰 3 行（定义+2 消费）且只在 1 个文件
chk "C3a-usage-lines" 3 "$(grep -rn 'OLLAMA_PORT' "$SRC" | wc -l)"
chk "C3b-usage-files" 1 "$(grep -rl 'OLLAMA_PORT' "$SRC" | wc -l)"

# C4 字面量不扩散: 11434 全 src 恰 1 处（即定义行; 消费走 ${OLLAMA_PORT}）
chk "C4-literal-unique" 1 "$(grep -rn '11434' "$SRC" | wc -l)"

# C5 消费活跃: ollamaUrl() 被调用 >= 1 次（排除定义行）
n=$(grep -rnF 'ollamaUrl()' "$SRC" | grep -v 'export function' | wc -l)
if [ "$n" -ge 1 ]; then echo "PASS C5-consumer-alive (calls=$n, 阈值>=1)"
else echo "FAIL C5-consumer-alive (calls=$n, 阈值>=1)"; rc=1; fi

# C6 后端对偶单源: MIA_OLLAMA_URL env 兜底文件集合全等 + environ.get 调用恰 2 处
files=$(grep -rl 'MIA_OLLAMA_URL' D:/m/workspace/mia_agent D:/m/workspace/office \
        --include='*.py' 2>/dev/null | sort | tr '\n' ';')
chk "C6a-backend-env-files" \
    "D:/m/workspace/mia_agent/tools.py;D:/m/workspace/office/routers/rag.py;" "$files"
chk "C6b-backend-env-calls" 2 \
    "$(grep -roF 'environ.get("MIA_OLLAMA_URL"' D:/m/workspace/mia_agent/tools.py D:/m/workspace/office/routers/rag.py 2>/dev/null | wc -l)"

echo "----"
if [ "$rc" = 0 ]; then echo "GRAY4 RESULT: PASS (exit 0)"
else echo "GRAY4 RESULT: FAIL (exit 1)"; fi
exit "$rc"
