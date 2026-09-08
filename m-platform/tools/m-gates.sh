#!/bin/bash
# m-gates.sh — M 平台安全门禁回归验证套（改守/改代理层后必跑）
# R10.4（评审C P3-1/评审A）：硬断言化——expect() 不符打 ✗ 并计数，结尾 FAILURES>0 则 exit 1；
# 门禁的价值就在于会喊红，不再靠人眼比对"期待401 实得200"。
# 用法: m-gates.sh   （exit 0=ALL GREEN / exit 1=有红灯）
# r24 起本文件=唯一维护源（PATH 侧同名件已是转发桩，双拷贝漂移断根）。
M_ROOT="${M_ROOT:-/d/m}"
PT=$(grep -o 'CODEBUDDY_PROXY_TOKEN=.*' "$M_ROOT/.env" | cut -d= -f2 | tr -d ' \r')
VT=$(grep -o 'VISION_PROXY_TOKEN=.*' "$M_ROOT/.env" | cut -d= -f2 | tr -d ' \r')
RT=$(grep -o 'RAG_PROXY_TOKEN=.*' "$M_ROOT/.env" | cut -d= -f2 | tr -d ' \r')
# 钥匙读取优先级：M_GATES_TOKEN 环境变量 → 维护者本机配置（$M_ROOT 下路径，按部署目录调整；CI/评审环境用 env 注入不落盘）
TOK="${M_GATES_TOKEN:-}"
if [ -z "$TOK" ]; then TOK=$(cat "$M_ROOT/guard/hostcopy.token" 2>/dev/null | tr -d ' \r'); fi
if [ -z "$TOK" ]; then TOK=$(python -c "import json,os;print(json.load(open(os.environ.get('M_ROOT','D:\\\\m')+'\\\\secrets\\\\.settings_secrets',encoding='utf-8')).get('general.apiToken',''))" 2>/dev/null); fi
FAILS=0
# R10.5（评审C P3）：--offline 模式跳过"真调上游"的活链断言（vision 200×2 每轮烧书生额度+上游闪断误红）；
# 默认全量（发布前跑），日常回归可 --offline。
LIVE=1
case "${1:-}" in --offline) LIVE=0;; esac

# expect <期待码> <curl 参数...>：状态码不符=✗+计数
expect() {
  local want="$1"; shift
  local got
  got=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$@")
  if [ "$got" = "$want" ]; then
    echo "✓ $got $*"
  else
    echo "✗ 期待$want 实得$got ← $*"
    FAILS=$((FAILS+1))
  fi
}

echo "── office 写门（401）──"
expect 401 -X POST http://127.0.0.1:2024/settings/general -H 'Content-Type: application/json' -d '{}'
expect 401 -X POST http://127.0.0.1:2024/files/save -H 'Content-Type: application/json' -d '{"name":"x","b64":"aGk="}'
expect 401 -X POST http://127.0.0.1:2024/approvals -H 'Content-Type: application/json' -d '{}'
echo "── office 读门（401/200）──"
expect 401 http://127.0.0.1:2024/settings
expect 200 http://127.0.0.1:2024/settings -H "Authorization: Bearer $TOK"
echo "── 豁免链（200）──"
expect 200 http://127.0.0.1:2024/health
expect 200 http://127.0.0.1:2024/settings/token/status
echo "── langgraph 原生 API（401）──"
expect 401 -X POST http://127.0.0.1:2024/assistants/search -H 'Content-Type: application/json' -d '{}'
echo "── 代理层（401/403）──"
expect 401 -X POST http://127.0.0.1:2024/codebuddy/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[]}'
expect 403 -X POST http://127.0.0.1:2024/codebuddy/chat/completions -H 'Content-Type: application/json' -H "X-Proxy-Key: $PT" -d '{"model":"gpt-evil","messages":[]}'
echo "── 沙箱隔离（workplatform 直连不可达 000 / 回环读面 401）──"
OUT=$(MSYS2_ARG_CONV_EXCL='*' docker exec m-sandbox-1 sh -c 'curl -s -o /dev/null -w "%{http_code}" --max-time 4 http://workplatform:8000/health; echo; curl -s -o /dev/null -w "%{http_code}" --max-time 4 http://host.docker.internal:2024/settings' 2>&1)
D=$(echo "$OUT" | sed -n 1p); H=$(echo "$OUT" | sed -n 2p)
if [ "$D" = "000" ]; then echo "✓ 沙箱直连 workplatform = $D（不可达）"; else echo "✗ 沙箱直连 workplatform 实得 $D"; FAILS=$((FAILS+1)); fi
if [ "$H" = "401" ]; then echo "✓ 沙箱回环读 settings = 401"; else echo "✗ 沙箱回环读 settings 实得 $H"; FAILS=$((FAILS+1)); fi
echo "── vision fail-closed（401/401/200/200）──"
expect 401 -X POST http://127.0.0.1:2024/vision -H 'Content-Type: application/json' -d '{"image_path":"/data/files/none.png","question":"x"}'
expect 401 -X POST http://127.0.0.1:2024/vision -H 'Content-Type: application/json' -H 'X-Proxy-Key: wrongkey' -d '{"image_path":"/data/files/none.png","question":"x"}'
if [ "$LIVE" = "1" ]; then
  expect 200 -X POST http://127.0.0.1:2024/vision -H 'Content-Type: application/json' -H "Authorization: Bearer $TOK" -d '{"image_b64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==","question":"说一个字"}'
  expect 200 -X POST http://127.0.0.1:2024/vision -H 'Content-Type: application/json' -H "X-Proxy-Key: $VT" -d '{"image_b64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==","question":"说一个字"}'
else
  echo "（--offline：跳过两条 vision 200 活链断言）"
fi
echo "── R10.5 XSS L2：Cookie 过守卫（对 cookie=200 / 错 cookie=401）──"
expect 200 http://127.0.0.1:2024/settings -H "Cookie: m_admin_token=$TOK"
expect 401 http://127.0.0.1:2024/settings -H "Cookie: m_admin_token=deadbeefdeadbeef"
echo "── 体积闸门（vision 9MB>8MB / codebuddy 3MB / rag 3MB / vision chunked，python 直发）──"
python /d/m/tools/_test_body_gates.py || FAILS=$((FAILS+1))
echo "── rag/query 二级钥匙（401/200/200）──"
expect 401 -X POST http://127.0.0.1:2024/rag/query -H 'Content-Type: application/json' -d '{"q_vec":[0.1],"k":3}'
expect 200 -X POST http://127.0.0.1:2024/rag/query -H 'Content-Type: application/json' -H "X-Proxy-Key: $RT" -d '{"q_vec":[0.1],"k":3}'
expect 200 -X POST http://127.0.0.1:2024/rag/query -H 'Content-Type: application/json' -H "Authorization: Bearer $TOK" -d '{"q_vec":[0.1],"k":3}'
echo "── 首设/清除限频窗（无钥匙 DELETE ×11 末次 429；不碰密钥本身）──"
LAST=""
for i in $(seq 1 11); do LAST=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -X DELETE http://127.0.0.1:2024/settings/token); done
if [ "$LAST" = "429" ]; then echo "✓ DELETE token ×11 末次 = 429"; else echo "✗ DELETE token ×11 末次实得 $LAST"; FAILS=$((FAILS+1)); fi
echo "── 读面补齐+skills 门（401 族/200）──"
expect 401 http://127.0.0.1:2024/models/all
expect 401 http://127.0.0.1:2024/usage/today
expect 401 http://127.0.0.1:2024/stats
expect 200 http://127.0.0.1:2024/skills/list -H "Authorization: Bearer $TOK"
expect 401 -X POST http://127.0.0.1:2024/skills/rehash
echo "── R10.8i：密码验证走 /verify_password（只验不签发；密码由管理员设置，此处探测端点可达）──"
PWCHECK=$(curl -s -m 8 -X POST http://127.0.0.1:9101/verify_password -H 'Content-Type: application/json' -H "X-Guard-Key: $(grep M_GUARD_KEY /d/m/.env | cut -d= -f2)" -d '{"password":"__probe__"}')
if echo "$PWCHECK" | grep -qE '"ok":\s*false'; then echo "✓ 密码探测端点可达（错误密码正确拒绝）: $PWCHECK"; else echo "✗ 密码探测异常: $PWCHECK"; FAILS=$((FAILS+1)); fi
echo "── R10.11（评审E P0-1）：/login 无钥匙 → 403（唯一能签发新密钥的端点必须带钥匙）──"
NKLOG=$(curl -s -o /dev/null -w "%{http_code}" -m 8 -X POST http://127.0.0.1:9101/login -H 'Content-Type: application/json' -d '{"password":"x"}')
if [ "$NKLOG" = "403" ]; then echo "✓ /login 无钥匙 = 403"; else echo "✗ /login 无钥匙实得 $NKLOG（期待403）"; FAILS=$((FAILS+1)); fi
echo "── approve/revoke 语义（r25 起 X-By 作废：fp 必填；只带暗号不带钥匙=401 绊线）──"
NT=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST http://127.0.0.1:2024/approvals -H 'Content-Type: application/json' -H 'X-By: admin' -d '{"thread_id":"gate-test","tool":"execute","fp":"deadbeefdeadbeef"}')
if [ "$NT" = "401" ]; then echo "✓ 旧暗号 X-By 无钥匙 = 401（假锁已拆，绊线成立）"; else echo "✗ 暗号仍能进门？实得 $NT"; FAILS=$((FAILS+1)); fi
for CASE in '{"thread_id":"gate-test","tool":"execute","fp":"deadbeefdeadbeef"}' '{"thread_id":"gate-test","tool":"execute"}'; do
  BODY=$(curl -s --max-time 10 -X POST http://127.0.0.1:2024/approvals -H 'Content-Type: application/json' -H "Authorization: Bearer $TOK" -d "$CASE")
  if echo "$BODY" | grep -q '"ok":false'; then echo "✓ approve ok:false ← ${CASE:0:50}"; else echo "✗ approve 未拒 ← $BODY"; FAILS=$((FAILS+1)); fi
done
RV=$(curl -s --max-time 10 -X DELETE http://127.0.0.1:2024/approvals -H 'Content-Type: application/json' -H "Authorization: Bearer $TOK" -d '{"thread_id":"gate-test","tool":"execute"}')
if echo "$RV" | grep -q '"ok"'; then echo "✓ DELETE /approvals 响应正常: $RV"; else echo "✗ DELETE /approvals 异常: $RV"; FAILS=$((FAILS+1)); fi
echo "── 前端 XSS L0 断言（rehype-raw/dangerouslySetInnerHTML/innerHTML 命中即红）──"
XH=$(grep -rn "rehype-raw\|dangerouslySetInnerHTML\|innerHTML" /d/m/deep-agents-ui/src --include=*.ts --include=*.tsx 2>/dev/null | wc -l)
if [ "$XH" = "0" ]; then echo "✓ XSS sink 命中 = 0"; else echo "✗ XSS sink 命中 $XH 处"; FAILS=$((FAILS+1)); fi
echo "── R10.8：进程身份豁免断言（容器内回环无 X-Internal-Key → 401）──"
IL=$(MSYS2_ARG_CONV_EXCL='*' docker exec m-workplatform-1 sh -c 'curl -s -o /dev/null -w "%{http_code}" --max-time 5 -X POST http://127.0.0.1:8000/assistants/search -H "Content-Type: application/json" -d "{}"' 2>/dev/null)
if [ "$IL" = "401" ]; then echo "✓ 容器内回环裸打原生 API = 401（助手 curl 链已断）"; else echo "✗ 容器内回环裸打实得 $IL（期待401）"; FAILS=$((FAILS+1)); fi
echo "── R10.8：guard 通信钥匙（无 X-Guard-Key → 403，沙箱挤兑链断；R10.11 含 /login）──"
NK=$(curl -s -o /dev/null -w "%{http_code}" -m 8 -X POST http://127.0.0.1:9101/verify -H 'Content-Type: application/json' -d '{"token":"x"}')
if [ "$NK" = "403" ]; then echo "✓ guard 无钥匙 verify = 403"; else echo "✗ guard 无钥匙实得 $NK"; FAILS=$((FAILS+1)); fi
echo "── secrets 卷账本实锤（②-1 修正=office 侧账本真落 /data/secrets/）──"
LED=$(docker exec m-workplatform-1 sh -c 'ls /data/secrets/ | grep -cE "usage|audit|bootstrap"' 2>/dev/null)
if [ "${LED:-0}" -ge 1 ]; then echo "✓ secrets 卷账本/服务商密钥文件数 = $LED"; else echo "✗ secrets 卷文件缺失"; FAILS=$((FAILS+1)); fi
echo "── 总结 ──"
if [ "$FAILS" = "0" ]; then echo "ALL GREEN"; exit 0; else echo "FAILURES: $FAILS"; exit 1; fi
