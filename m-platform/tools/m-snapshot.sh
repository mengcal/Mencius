#!/bin/bash
# m-snapshot.sh <标签> — M 平台改动集快照（改码前必备份）
# 用法: m-snapshot.sh pre-r84
# R10.9：固定清单在 office/、mia_agent/ 拆分后漏掉两个新包（快照=保命绳，漏=白拍）
#   ——改 rglob 递归收集 workspace 源码（排除 __pycache__/.venv/mia_home 数据区）+前端 src 全量。
TAG="${1:-snap-$(date +%Y%m%d-%H%M%S)}"
cd /d/m && python - "$TAG" <<'PYEOF'
import zipfile, os, sys, time
from pathlib import Path
tag = sys.argv[1]
out = zipfile.ZipFile(rf'D:\m\backups\{tag}-{time.strftime("%Y%m%d-%H%M%S")}.zip', 'w', zipfile.ZIP_DEFLATED)
for f in ['docker-compose.yml', '.env', 'langgraph.json']:
    p = os.path.join(r'D:\m', f)
    if os.path.exists(p):
        out.write(p, f)
# workspace 递归：源码+配置全收，排除数据区/缓存/虚拟环境
WS = Path(r'D:\m\workspace')
INC_EXT = ('.py', '.json', '.html')
for p in sorted(WS.rglob('*')):
    if not p.is_file():
        continue
    rel = p.relative_to(WS).as_posix()
    if any(e in rel for e in ('__pycache__', 'mia_home/', '.venv', 'venv/', '.git', 'node_modules')):
        continue
    if rel.endswith(INC_EXT) or rel in ('Dockerfile', 'langgraph.json'):
        out.write(str(p), 'workspace/' + rel)
# 前端 src 全量
for root, dirs, fs in os.walk(r'D:\m\deep-agents-ui\src'):
    dirs[:] = [d for d in dirs if d != 'node_modules']
    for fn in fs:
        if fn.endswith(('.ts', '.tsx')):
            p = os.path.join(root, fn)
            out.write(p, 'fe/' + os.path.relpath(p, r'D:\m\deep-agents-ui\src').replace('\\', '/'))
out.close()
print('snapshot:', out.filename)
PYEOF
