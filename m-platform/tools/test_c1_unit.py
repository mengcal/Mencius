"""C1 v2 单测（r41b，四家审查合批后）：单源映射/自包含拒出口/SubGate/启动断言/email 矩阵。
含一条不打 patch 的真实路径冒烟（NOVA P0-3：单测盲区教训）。容器内跑。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import ToolMessage
from mia_agent.confirm_gate_c1 import ConfirmGateC1, SubGate, assert_gate_order
from mia_agent.confirm_gate import ConfirmGateMiddleware

ok = 0


def T(name, cond):
    global ok
    assert cond, name
    ok += 1
    print("PASS", name)


gate = ConfirmGateC1()
LEV = ConfirmGateMiddleware._level  # 真实现（不 patch 的冒烟用）

# ---- 单源映射（Cora P1-1）：_route 与 _decision 永一致——用真档位跑冒烟 ----
cur = LEV()
T(f"冒烟-真档位({cur})只读走", gate._route("read_file", {}) in ("pass",))
T("冒烟-真档位自锁拒", gate._route("write_file", {"path": "D:/m/workspace/approvals.py"}) == "to_deny")

# ---- 四档路由（patch _level 单一位置——真源在 _decision，_route 只是映射）----
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "plan")):
    T("plan-只读放行", gate._route("read_file", {}) == "pass")
    T("plan-变更转拒", gate._route("write_file", {"path": "x"}) == "to_deny")
    T("plan-email-send拒", gate._route("email", {"action": "send", "to": "a@b.c"}) == "to_deny")
    T("plan-email-list放", gate._route("email", {"action": "list"}) == "pass")
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    T("strict-写类弹卡", gate._route("write_file", {"path": "notes/a.md"}) == "ask")
    T("strict-执行弹卡", gate._route("execute", {"command": "ls"}) == "ask")
    T("strict-email-send弹卡", gate._route("email", {"action": "send"}) == "ask")
    T("strict-未知MCP弹卡", gate._route("mcp__unknown__call", {}) == "ask")
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "auto_edit")):
    T("auto_edit-软写放行", gate._route("edit_memory", {"k": "v"}) == "pass")
    T("auto_edit-email-send弹卡", gate._route("email", {"action": "send"}) == "ask")
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "full")):
    T("full-写类放行", gate._route("write_file", {"path": "x"}) == "pass")
    T("full-自锁仍拒", gate._route("write_file", {"path": "D:/m/workspace/settings.json"}) == "to_deny")

# ---- when 谓词双向 ----
when = gate._make_when("write_file")
class FakeReq:
    def __init__(self, args): self.tool_call = {"name": "write_file", "args": args, "id": "x"}
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    T("when-ask真", when(FakeReq({"path": "a"})) is True)
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "plan")):
    T("when-deny让行", when(FakeReq({"path": "a"})) is False)

# ---- C1.wrap_tool_call 自包含拒出口（Lyra P0）----
class FakeExecReq:
    def __init__(self, name, args): self.tool_call = {"name": name, "args": args, "id": "id1"}
def fake_handler(req):
    return "EXECUTED"
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "plan")):
    r = gate.wrap_tool_call(FakeExecReq("write_file", {"path": "x"}), fake_handler)
    T("C1自拒-plan写类拒信", isinstance(r, ToolMessage) and "计划模式" in r.text)
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "full")):
    r = gate.wrap_tool_call(FakeExecReq("write_file", {"path": "D:/m/workspace/approvals.py"}), fake_handler)
    T("C1自拒-full自锁拒信", isinstance(r, ToolMessage) and "锁" in r.text)
    r2 = gate.wrap_tool_call(FakeExecReq("write_file", {"path": "notes/d.md"}), fake_handler)
    T("C1放行-full正常写执行", r2 == "EXECUTED")

# ---- SubGate：ask 也转文案（子层不弹卡）----
sg = SubGate()
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    r = sg.wrap_tool_call(FakeExecReq("execute", {"command": "rm x"}), fake_handler)
    T("SubGate-ask转文案不执行", isinstance(r, ToolMessage))
    r2 = sg.wrap_tool_call(FakeExecReq("read_file", {"path": "x"}), fake_handler)
    T("SubGate-只读放行", r2 == "EXECUTED")

# ---- 启动断言（Lyra P0 配套）----
try:
    assert_gate_order([object()])
    raise AssertionError("缺 C1 未抛")
except ValueError:
    T("启动断言-缺C1炸", True)
try:
    assert_gate_order([ConfirmGateC1(), SubGate()])
    T("启动断言-主图C1在列过", True)
except ValueError:
    raise AssertionError("C1 在列不该炸")

# ---- 官方 fail-closed 复验 ----
try:
    from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
    bare = HumanInTheLoopMiddleware.__new__(HumanInTheLoopMiddleware)
    HumanInTheLoopMiddleware.__init__(bare, interrupt_on={"x": {"allowed_decisions": []}})
    raise AssertionError("空 decisions 未抛")
except ValueError:
    T("官方fail-closed复验", True)

# ---- 动态反选注册 ----
class FakeAI:
    def __init__(self, calls): self.tool_calls = calls
state = {"messages": [FakeAI([{"name": "mcp__fresh__t", "args": {}, "id": "c1"}])]}
with patch("langchain.agents.middleware.human_in_the_loop.HumanInTheLoopMiddleware.after_model",
           lambda self, s, r: "SUPER"):
    gate.after_model(state, runtime=None)
T("动态反选-新名已注册", "mcp__fresh__t" in gate.interrupt_on)

# ---- r41 网关批准卡预算（hy4 修正版语义：幂等/隔离/精准拒/不吞批准）----
import approvals as _ap
_ap._task_cards.clear(); _ap._counted_tc.clear(); _ap._card_pressure_soft.clear(); _ap._turn_marks.clear()
tid_probe = "test-budget-thread"
# 幂等：同 (tid,tc_id) 多求值只计一次（resume 重放场景）
_ap.bump_blocked(tid_probe, "tc-dup")
_ap.bump_blocked(tid_probe, "tc-dup")
_ap.bump_blocked(tid_probe, "tc-dup")
T("resume 重放幂等", _ap.task_cards(tid_probe) == 1)
for i in range(8):
    _ap.bump_blocked(tid_probe, f"tc-{i}")
T("8 张达预算线", _ap.card_pressure(tid_probe) == "BUDGET")
# r2-2 双轨后：告警文案看软轨，构造场景须两轨同改（语义演进，合法更新）
_ap._task_cards[tid_probe] = [4, 0]; _ap._card_pressure_soft[tid_probe] = 4
T("4 张告警不报数", "⚠" in _ap.card_pressure(tid_probe) and "8" not in _ap.card_pressure(tid_probe))
_ap._task_cards[tid_probe] = [2, 0]; _ap._card_pressure_soft[tid_probe] = 2
T("2 张静默", _ap.card_pressure(tid_probe) == "")
# over_budget 精准拒：被预算扣卡的拒，爸爸批过的不吞
with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    gate2 = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: tid_probe)):
        # FakeExecReq 的 tc id="id1"：不在扣卡集合里 → 不吞（爸爸刚批的调用=这情形）
        gate2._over_budget[tid_probe] = {"tc-other"}
        r = gate2.wrap_tool_call(FakeExecReq("execute", {"command": "ls"}), fake_handler)
        T("预算外调用不误伤（不吞批准）", r == "EXECUTED")
        # 在扣卡集合里的：精准拒，且拒一次即消费
        class DeniedReq:
            tool_call = {"name": "execute", "args": {"command": "ls"}, "id": "tc-x"}
        gate2._over_budget[tid_probe] = {"tc-x"}
        r3 = gate2.wrap_tool_call(DeniedReq(), fake_handler)
        T("被预算扣卡的精准拒", isinstance(r3, ToolMessage) and "预算" in r3.text)
        r4 = gate2.wrap_tool_call(DeniedReq(), fake_handler)
        T("拒一次即消费（防集合膨胀）", r4 == "EXECUTED")
_ap._task_cards.clear(); _ap._counted_tc.clear(); _ap._card_pressure_soft.clear(); _ap._turn_marks.clear()

# NO-TID：不进桶不耗预算、卡照弹
with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "")), \
     patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    gate3 = ConfirmGateC1()
    w = gate3._make_when("execute")
    class R: tool_call = {"name": "execute", "args": {"command": "x"}, "id": "abc"}
    T("NO-TID 不弹卡不受桶锁", w(R()) is True and _ap.task_cards("") == 0)

print(f"\n{ok} 项全绿")
