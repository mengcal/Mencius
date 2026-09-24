#!/usr/bin/env bash
# =============================================================================
# 灰区 #1 —— lark.py 飞书密钥载体（自由文本 + 正则抠，未入 secrets 键值体系）
# 依据: D:/m/docs/acceptance-checklist-v1.md 0.5 表 #1（09-19 评估后缓办）
# 验收口径: 挂账形态零漂移 + 4 条安全不变量。全机械可判: 字符串命中数 /
#           文件存在性 / 引用面文件数 / 字节比对退出码。禁主观措辞。
# 运行环境: Git Bash (Windows)。用法: bash gray1_lark_cred.sh
# 退出码: 0 = 全部通过; 1 = 任一检查失败（FAIL 行即定位）
# 产出: CB glm-5.3（烧分战役⑦，09-22）；落盘/跑验: 知夏
# =============================================================================
set -u
LARK="D:/m/workspace/office/routers/lark.py"
CRED="D:/m/workspace/secrets/lark_app.txt"
COMPOSE="D:/m/docker-compose.yml"
MIRROR="D:/m/mencius-push/m-platform/workspace/office/routers/lark.py"
rc=0

chk() {  # $1=检查名 $2=期望值 $3=实得值
  if [ "$2" = "$3" ]; then printf 'PASS %s expected=%s actual=%s\n' "$1" "$2" "$3"
  else printf 'FAIL %s expected=%s actual=%s\n' "$1" "$2" "$3"; rc=1; fi
}

# ---- 挂账形态零漂移（锚定内容唯一性; 行号漂移另行打印供对账）----

# C1 载体定义: secrets/lark_app.txt 恰 1 处
chk "C1-cred-file-def" 1 "$(grep -cF '_CRED_FILE = BASE / "secrets" / "lark_app.txt"' "$LARK")"
# C2 正则抠形态: App ID 正则与 Secret 正则各恰 1 处
chk "C2a-appid-regex"  1 "$(grep -cF '(cli_[0-9a-f]+)' "$LARK")"
chk "C2b-secret-regex" 1 "$(grep -cF 'secret\s*[=:：]\s*(\S+)' "$LARK")"
# C3 缓办未动工: 未接 secrets 键值体系（secret_get 零命中）
chk "C3-not-migrated" 0 "$(grep -c 'secret_get' "$LARK")"
# INFO 当前行号（与 0.5 表登记比对用, 不作闸）
echo "INFO lines: $(grep -nF '_CRED_FILE' "$LARK" | head -1 | cut -d: -f1) (0.5 表登记 23-29)"

# ---- 安全不变量 ----

# C4 凭据文件活体: 存在且非空; 内容形状与两条正则匹配（只输出计数, 不回显任何内容）
if [ -s "$CRED" ]; then echo "PASS C4a-cred-exists-nonempty"
else echo "FAIL C4a-cred-exists-nonempty ($CRED)"; rc=1; fi
n=$(grep -cE 'cli_[0-9a-f]+' "$CRED" || true)
if [ "${n:-0}" -ge 1 ]; then echo "PASS C4b-cred-appid-shape (hits=$n)"
else echo "FAIL C4b-cred-appid-shape (hits=0, 阈值>=1)"; rc=1; fi
n=$(grep -ciE 'secret[[:space:]]*[=:]' "$CRED" || true)
if [ "${n:-0}" -ge 1 ]; then echo "PASS C4c-cred-secret-shape (hits=$n)"
else echo "FAIL C4c-cred-secret-shape (hits=0, 阈值>=1)"; rc=1; fi

# C5 token/secret 不落盘不打印: 写文件与 print 均零命中（全文件仅 read_text 读凭据）
chk "C5a-no-write" 0 "$(grep -cE 'write_text|\.write\(|open\(' "$LARK")"
chk "C5b-no-print" 0 "$(grep -c 'print(' "$LARK")"

# C6 审计脱敏: 只记前 8 位+长度; 审计参数含 token/secret 变量 = 0 处
chk "C6a-audit-redact"  1 "$(grep -cF 'to=receive_id[:8]' "$LARK")"
chk "C6b-audit-no-token" 0 "$(grep -cE '_token_audit\([^)]*(token|secret)' "$LARK")"

# C7 沙箱挂载面: compose 中 lark 零命中（凭据文件不进任何容器挂载）
chk "C7-compose-no-lark" 0 "$(grep -ci 'lark' "$COMPOSE")"

# C8 引用面封闭: lark_app 代码引用（仅 .py，排除 .git/pyc 二进制噪音）恰 2 个文件
chk "C8-ref-surface-files" 2 "$(grep -rlF --include='*.py' 'lark_app' D:/m/workspace D:/m/guard 2>/dev/null | wc -l)"

# C9 镜像同步: push 镜像与真码逐字节一致
if cmp -s "$LARK" "$MIRROR"; then echo "PASS C9-mirror-identical"
else echo "FAIL C9-mirror-identical ($MIRROR)"; rc=1; fi

echo "----"
if [ "$rc" = 0 ]; then echo "GRAY1 RESULT: PASS (exit 0)"
else echo "GRAY1 RESULT: FAIL (exit 1)"; fi
exit "$rc"
