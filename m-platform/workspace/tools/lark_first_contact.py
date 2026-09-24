import sys
import os
sys.path.insert(0, "/deps/outer-workspace/src" if os.path.isdir("/deps/outer-workspace/src") else r"D:\m\workspace")
import json
import re
import pathlib
import httpx

# 读凭据（手机号脱敏处理：查询后不回显）
t = pathlib.Path("/deps/outer-workspace/src/secrets/lark_app.txt" if os.path.isdir("/deps/outer-workspace/src")
                 else r"D:\m\workspace\secrets\lark_app.txt").read_text(encoding="utf-8", errors="replace")
phone = re.search(r"(?i)phone\s*[=:：]\s*(\+?\d{6,15})", t)
if not phone:
    print("NO-PHONE：lark_app.txt 里没找到 Phone= 行")
    sys.exit(0)

# 容器内跑（桥只用 httpx；office.routers.lark 复用已验证的取 token 逻辑）
from office.routers.lark import tenant_token

tok = tenant_token()
r = httpx.post("https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
               headers={"Authorization": f"Bearer {tok}"},
               json={"mobiles": [phone.group(1) if phone.group(1).startswith("+") else "+86" + phone.group(1)]},
               timeout=15)
if r.status_code != 200 or not r.text.strip().startswith("{"):
    print("HTTP", r.status_code, "原始响应:", r.text[:200])
    sys.exit(0)
j = r.json()
if j.get("code") != 0:
    print("查询失败:", j.get("code"), str(j.get("msg"))[:150])
    sys.exit(0)
users = (j.get("data") or {}).get("user_list") or []
if not users or not users[0].get("user_id"):
    print("查无此人（手机号或应用权限问题）")
    sys.exit(0)
open_id = users[0]["user_id"]
print("open_id 取到:", open_id[:6] + "***")

# 存进 settings.lark.dad_open_id
_sp = "/deps/outer-workspace/src/settings.json" if os.path.isdir("/deps/outer-workspace/src") else r"D:\m\workspace\settings.json"
sp = pathlib.Path(_sp)
s = json.loads(sp.read_text(encoding="utf-8"))
s.setdefault("lark", {})["dad_open_id"] = open_id
sp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
print("已存 settings.lark.dad_open_id")

# 第一条测试消息直发（桥层测试，工具层的批准门由 C1 管、不在此处）
from office.routers.lark import send_text
res = send_text("米娅上线测试 ✅ 飞书桥打通了——以后我有事找您批，这里会响。—— 您的 Mia")
print("发送结果:", res.get("ok"), res.get("error", "")[:120])
