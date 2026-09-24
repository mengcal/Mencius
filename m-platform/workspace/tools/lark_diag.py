import sys
import os
sys.path.insert(0, "/deps/outer-workspace/src" if os.path.isdir("/deps/outer-workspace/src") else r"D:\m\workspace")
import httpx
from office.routers.lark import tenant_token

tok = tenant_token()
import json
import pathlib
sp = "/deps/outer-workspace/src/settings.json" if os.path.isdir("/deps/outer-workspace/src") else r"D:\m\workspace\settings.json"
oid = json.loads(pathlib.Path(sp).read_text(encoding="utf-8"))["lark"]["dad_open_id"]

# 发一条并拿 message_id
r = httpx.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
               headers={"Authorization": f"Bearer {tok}"},
               json={"receive_id": oid, "msg_type": "text",
                     "content": json.dumps({"text": "📡 诊断消息（带 message_id 回执）——若看不到这条，多半是应用可用范围没包含您，或消息在 Mia 机器人会话里未打开"}, ensure_ascii=False)},
               timeout=15)
j = r.json()
print("send code:", j.get("code"), "msg:", str(j.get("msg"))[:80])
mid = (j.get("data") or {}).get("message_id", "")
print("message_id:", mid[:24])
if mid:
    # 查这条消息的下发状态
    r2 = httpx.get(f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}",
                   headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    j2 = r2.json()
    d2 = j2.get("data") or {}
    items = d2.get("items") or []
    print("查询 code:", j2.get("code"), "消息存在:", bool(items))
    if items:
        print("会话类型:", (items[0].get("chat_id") or "")[:10], "发送时间 ok")
