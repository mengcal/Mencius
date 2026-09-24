# -*- coding: utf-8 -*-
"""r61c HTTP 链辅助：cb-post 子钥→0600 安全临时 curl 配置（键值永不打印）。"""
import sys, os, tempfile
sys.path.insert(0, "/deps/outer-workspace/src")
from mia_agent.external_guard import hkdf_subkey
from settings_mgr import secret_get

mk = (secret_get("external.master_key") or "").encode("utf-8")
if not mk:
    print("NOKEY")
    sys.exit(1)
sk = hkdf_subkey(mk, "cb-post").hex()
fd, path = tempfile.mkstemp(prefix="r61c_", suffix=".hdr")
with os.fdopen(fd, "w") as f:
    f.write(f'header = "Authorization: Bearer {sk}"\n')
os.chmod(path, 0o600)
print(path)
