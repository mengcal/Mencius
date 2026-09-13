# -*- coding: utf-8 -*-
"""r46 单测：execute 路径形态硬拒（when=False 不弹卡 + wrap 教学拒信）。"""
import sys
sys.path.insert(0, "/deps/outer-workspace/src")

ok, fail = 0, []


def T(name, cond):
    global ok
    if cond:
        ok += 1
    else:
        fail.append(name)
        print("  FAIL", name)


from unittest.mock import patch  # noqa: E402
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402
from mia_agent.acceptance_kit import check_path_form  # noqa: E402

with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "t-abs")):
        # when 层：绝对形式 → False（不弹卡）
        class R:
            def __init__(self, cmd, tcid):
                self.tool_call = {"name": "execute", "id": tcid, "args": {"command": cmd}}
        w = g._make_when("execute")
        T("绝对形式 when=False", w(R("ls -la /notes/", "tc-a")) is False)
        T("全盘 find when=False", w(R("find / -name x", "tc-b")) is False)
        T("相对路径 when=True", w(R("ls -la notes/", "tc-c")) is True)
        T("写落点绝对形式 when=False", w(R("echo x > /notes/y", "tc-d")) is False)
        # wrap 层：拒信带教学
        msg = g._check_budget_gate(R("ls -la /notes/", "tc-a"))
        T("wrap 拒信=ToolMessage 教学文案", msg is not None and "相对路径" in msg.content and "/notes" in msg.content)
        T("消费后集合清（防膨胀）", "tc-a" not in (g._abs_blocked.get("t-abs") or set()))

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
