#!/usr/bin/env bash
# =============================================================================
# 灰区 #5 —— misc.py _DEF_LIMIT = 131072（schema 读取失败时的最后防线）
# 定性: 有意设计（行注释声明）——但"兜底常数 == schema 默认值"目前靠人肉，
#       本脚本把该恒等关系钉成机械闸。
# 依据: D:/m/docs/acceptance-checklist-v1.md 0.5 表 #5
# 验收口径: 兜底唯一 + 行号不漂移 + 主路径双读 schema + 双源恒等 + 字面量不扩散
#           + 运行态覆盖类型合法。全机械可判。
# 退出码: 0 = 全部通过; 1 = 任一失败
# 产出: CB glm-5.3（烧分战役⑦，09-22）；落盘/跑验: 知夏
# =============================================================================
set -u
MISC="D:/m/workspace/office/routers/misc.py"
SCHEMA="D:/m/workspace/settings_schema.py"
SETTINGS="D:/m/workspace/settings.json"
rc=0

chk() {
  if [ "$2" = "$3" ]; then printf 'PASS %s expected=%s actual=%s\n' "$1" "$2" "$3"
  else printf 'FAIL %s expected=%s actual=%s\n' "$1" "$2" "$3"; rc=1; fi
}

# C1 兜底唯一且声明同行: 定义+注释整行恰 1 处
chk "C1-fallback-unique" 1 \
  "$(grep -cF '_DEF_LIMIT = 131072  # schema 读取失败时的最后防线' "$MISC")"

# C2 行号不漂移: 定义行号 == 0.5 表登记的 111（漂移即 fail, 须回灌对账验收单）
line=$(grep -nF '_DEF_LIMIT = 131072' "$MISC" | head -1 | cut -d: -f1)
chk "C2-line-no-drift" 111 "${line:-0}"

# C3 主路径优先: _dof("models.contextLimitDefault") 恰 2 次（misc.py:109 双读:
#    get 缺省 + or 兜底——防线只在两条 schema 读取路都失败时生效）
chk "C3-schema-reads" 2 "$(grep -oF '_dof("models.contextLimitDefault")' "$MISC" | wc -l)"

# C4 双源恒等: schema 默认值 == 131072（不等 = 防线偏离单一源, 最高优先级失败项）
v=$(python -c "import importlib.util as u; s=u.spec_from_file_location('ss', r'D:/m/workspace/settings_schema.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(m.SCHEMA['models.contextLimitDefault']['default'])" 2>/dev/null)
chk "C4-schema-default-eq" 131072 "${v:-ERR}"

# C5 字面量不扩散: 131072 在 workspace py 码面恰 4 行（schema:20/21 + misc:98/111;
#    mia_home/backups/.venv 第三方区不计）——逐行打印供人工比对
n=$(grep -rn '131072' D:/m/workspace --include='*.py' 2>/dev/null | grep -vc 'mia_home\|backups\|\.venv')
chk "C5-literal-lines" 4 "$n"
grep -rn '131072' D:/m/workspace --include='*.py' 2>/dev/null \
  | grep -v 'mia_home\|backups\|\.venv' | sed 's/^/  HIT /'

# C6 运行态覆盖合法: settings.json 若覆盖 contextLimitDefault, 值必须为 int
#    （非 int = 每次请求都落入防线分支, 单一源名存实亡）
if [ ! -f "$SETTINGS" ]; then
  echo "PASS C6-override-int-or-absent (settings.json absent -> schema 默认路)"
else
  o=$(python -c "import json; d=json.load(open(r'D:/m/workspace/settings.json', encoding='utf-8')); v=(d.get('models') or {}).get('contextLimitDefault', 'ABSENT'); print(v if isinstance(v, int) else ('ABSENT' if v == 'ABSENT' else 'BADTYPE'))" 2>/dev/null)
  case "$o" in
    ABSENT|[0-9]*) echo "PASS C6-override-int-or-absent (value=$o)" ;;
    *) echo "FAIL C6-override-int-or-absent (value=$o, 期望 int 或 ABSENT)"; rc=1 ;;
  esac
fi

echo "----"
if [ "$rc" = 0 ]; then echo "GRAY5 RESULT: PASS (exit 0)"
else echo "GRAY5 RESULT: FAIL (exit 1)"; fi
exit "$rc"
