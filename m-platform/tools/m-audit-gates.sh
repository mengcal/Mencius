#!/bin/bash
# m-audit-gates.sh — 守名单↔前端消费点 对账（R10 流程硬化，评审B 建议：改守必查配套，防"改一漏一"第四次）
# 原理：从 office/app.py 提取 _TOKEN_GUARDED/_GET_GUARDED 名单 → 对每条路径 grep 前端 src →
#       报告每个消费点所在文件行，并粗查该行附近 20 行内有无 authHeaders/Bearer 痕迹。
# R10.11（评审E P1-1 假绿修复）：原版读单文件 office.py——拆分后成 11 行壳、名单 0 命中、
#       脚本空转恒报"全部配套 ✓"。现改读 office/app.py（名单真身），并加"名单为空=报警"保险。
# 双拷贝纪律（r23 教训）：本文件为唯一维护源；任何 PATH 副本只准转发不准承载逻辑。
# r2（hy4 自测 P2-1，09-07 晚）：保险丝补"消费点侧"——FE 失存 / grep rc=2 /
#       名单符号逐个硬检（防并集半瞎）/ 命中总数为 0，任一异常即报警作废，禁止静默盖章"全部配套 ✓"。
# 用法: m-audit-gates.sh
python - <<'EOF'
import re, subprocess, os

OFFICE = r'D:\m\workspace\office\app.py'
FE = r'D:\m\deep-agents-ui\src'
if not os.path.isdir(FE):
    raise SystemExit(f'!! 前端源树不存在: {FE}——消费点侧失联，本报告作废（假绿保险 r2 禁静默通过）')
src = open(OFFICE, encoding='utf-8').read()

def grab(name):
    m = re.search(name + r'\s*=\s*\(([^)]*)\)', src)
    if not m:
        raise SystemExit(f'!! 名单符号 {name} 在 {OFFICE} 失配——本报告作废（逐符号硬检，r2 防并集半瞎）')
    out = [p.strip().strip('",\' ') for p in m.group(1).replace('\n', ' ').split(',') if p.strip().startswith('"')]
    if not out:
        raise SystemExit(f'!! 名单 {name} 抓到 0 条——报告作废（r2）')
    return out

guarded = set(grab('_TOKEN_GUARDED')) | set(grab('_GET_GUARDED'))
if not guarded:
    raise SystemExit('!! 守卫名单为空——office/app.py 路径或名单符号变了（R10.11 假绿保险：空名单=报警，禁止静默通过）')
print('受守路径:', sorted(guarded))
problems = 0
total_hits = 0
for path in sorted(guarded):
    frag = path.strip('/')
    if not frag:
        continue
    # 前端所有引用该 API 路径的行
    r = subprocess.run(['grep', '-rn', f'/{frag}', FE, '--include=*.ts', '--include=*.tsx'],
                       capture_output=True, text=True)
    if r.returncode not in (0, 1):  # grep rc=2 含目录/权限错误——失联不得当"无消费点"混过
        raise SystemExit(f'!! grep {path} 异常 rc={r.returncode}: {r.stderr.strip()[:120]}——报告作废（r2 消费点侧保险）')
    hits = [l for l in r.stdout.splitlines() if 'node_modules' not in l and ('fetch(' in l or '${API}' in l or 'API}/' in l)]
    total_hits += len(hits)
    for h in hits:
        mm = re.match(r'^(.+?):(\d+):', h)  # 盘符 D: 后不接数字，非贪婪正确匹配到 file:行号:
        if not mm:
            continue
        f, ln = mm.group(1), int(mm.group(2))
        lines = open(f, encoding='utf-8', errors='ignore').read().splitlines()
        window = '\n'.join(lines[max(0, ln - 6):ln + 14])
        ok = ('authHeaders' in window) or ('Authorization' in window) or ('getAdminToken' in window)
        mark = '✓' if ok else '✗ 缺钥匙'
        if not ok:
            problems += 1
        print(f'{mark} {path} → {os.path.basename(f)}:{ln}')
if total_hits == 0:
    raise SystemExit('!! 受守路径全部零前端消费点——消费侧静默，报告作废（r2 总下限保险）')
print()
print('结论:', '全部配套 ✓' if problems == 0 else f'!! {problems} 个消费点缺鉴权配套——改守忘带钥匙，修完再上线')
EOF
