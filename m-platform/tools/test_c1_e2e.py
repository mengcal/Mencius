"""C1 必测1（Eve P0 级存疑）：官方 after_model 真跑（interrupt monkeypatch）——
approve 恢复 TC 保留 / reject 后 error ToolMessage 插入。NOVA 送的假 decisions 法。"""
import sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import langchain.agents.middleware.human_in_the_loop as m
from mia_agent.confirm_gate_c1 import ConfirmGateC1
from mia_agent.confirm_gate import ConfirmGateMiddleware
from langchain_core.messages import AIMessage

ok = 0


def T(name, cond):
    global ok
    assert cond, name
    ok += 1
    print("PASS", name)


gate = ConfirmGateC1()
fake_runtime = SimpleNamespace(context=None, stream_writer=None, store=None,
                               execution_info=None, server_info=None)


def run(decisions):
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "write_file", "args": {"path": "notes/x.md", "content": "hi"}, "id": "t1"},
    ])]}
    orig = m.interrupt
    m.interrupt = lambda req: {"decisions": decisions}
    try:
        with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
            out = gate.after_model(state, fake_runtime)
    finally:
        m.interrupt = orig
    return out


out = run([{"type": "approve"}])
ai = out["messages"][0]
T("approve-TC保留待执行", ai.tool_calls and ai.tool_calls[0]["id"] == "t1")

out = run([{"type": "reject", "message": "别写这个"}])
ai = out["messages"][0]
tm = [x for x in out["messages"] if getattr(x, "type", "") == "tool"]
T("reject-TC保留在AIMessage", ai.tool_calls and ai.tool_calls[0]["id"] == "t1")
T("reject-error信插入", len(tm) == 1 and tm[0].status == "error")
T("reject-带reason文案", "别写这个" in str(tm[0].content))
# NOVA P0-1 实证：带 reason 时官方不给勿重试文案——前端 reject 不带 message 才走勿重试分支
T("NOVA P0-1复现-带reason无勿重试", "Do not retry" not in str(tm[0].content))

out = run([{"type": "reject"}])
tm = [x for x in out["messages"] if getattr(x, "type", "") == "tool"]
T("reject-空reason有勿重试", "Do not retry" in str(tm[0].content))

print(f"\n{ok} 项全绿（必测1 过：approve 恢复=TC 保留、reject=error 信入 state）")
