"""test_rev_race.py —— 双窗口 409 竞态的打桩闭环测试（爸爸真机项清账）
语义等价性：双窗口场景的本质 = 客户端 B 持旧 rev 保存被 409 拒。直接双发调
api_set_settings（绕过 HTTP/auth 层，rev 比对+保存逻辑原样走真代码+真 settings.json）。
全程只动 scribe.agingDays，测完恢复原值。
"""
import asyncio, sys, os, json

sys.path.insert(0, r"D:\m\workspace")
from office.routers.providers import api_set_settings
from settings_mgr import load_settings, settings_rev
from types import SimpleNamespace

req = SimpleNamespace(client=SimpleNamespace(host="racetest"))
PASS, FAIL = [], []
def T(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("✓" if cond else "✗"), name)

async def main():
    orig = load_settings().get("scribe", {}).get("agingDays")
    rev1 = settings_rev()

    # 窗口 A：持新 rev 保存（agingDays 30→31）
    r1 = await api_set_settings("scribe", {"agingDays": 31, "_rev": rev1}, req)
    ok1 = (r1.status_code == 200 if hasattr(r1, "status_code") else r1.get("ok"))
    new_rev = r1.body and json.loads(r1.body).get("rev") if hasattr(r1, "body") and isinstance(r1.body, (bytes, bytearray)) else (r1.get("rev") if isinstance(r1, dict) else None)
    T("窗口 A 持新 rev 保存成功", bool(ok1))
    print("  A 返回 rev:", new_rev)

    # 窗口 B：持【旧 rev】保存（模拟 B 页面加载后未刷新）→ 必 409
    r2 = await api_set_settings("scribe", {"agingDays": 30, "_rev": rev1}, req)
    code2 = r2.status_code if hasattr(r2, "status_code") else 200
    body2 = json.loads(r2.body) if hasattr(r2, "body") and isinstance(r2.body, (bytes, bytearray)) else r2
    T("窗口 B 持旧 rev 被 409 拒", code2 == 409)
    T("409 响应带 conflict 标记", body2.get("conflict") is True)
    T("409 文案是中文人话", "已被后台修改" in str(body2.get("error", "")))

    # 窗口 B 刷新后持新 rev 保存 → 成功（死循环已破）
    rev3 = settings_rev()
    r3 = await api_set_settings("scribe", {"agingDays": 30, "_rev": rev3}, req)
    ok3 = (r3.status_code == 200 if hasattr(r3, "status_code") else r3.get("ok"))
    T("窗口 B 刷新拿新 rev 后保存成功（409 死循环已破）", bool(ok3))

    # 恢复原值
    now = load_settings().get("scribe", {}).get("agingDays")
    if now != orig:
        rev_now = settings_rev()
        await api_set_settings("scribe", {"agingDays": orig, "_rev": rev_now}, req)
    final = load_settings().get("scribe", {}).get("agingDays")
    T("原值恢复（agingDays=%s）" % orig, final == orig)

    print("\n%d 项全绿" % len(PASS) if not FAIL else "\n失败: %s" % FAIL)
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
