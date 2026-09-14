# -*- coding: utf-8 -*-
"""r61e C1 落账钩子版本钉测试（Nova 方案回归件）：
喂 approve/edit/reject 三种 decision 直调 _process_decision，断言
①钩子触发落账 c1_decision ②官方语义不扰（approve 原样/edit 换参/reject 出 ToolMessage）。
langchain 升级后必跑此件——私有方法签名变了这里先红。"""
import sys, json, tempfile, os
sys.path.insert(0, "/deps/outer-workspace/src")
from unittest.mock import patch
import approvals as ap  # noqa: E402
from mia_agent.confirm_gate_c1 import ConfirmGateC1  # noqa: E402
from mia_agent.confirm_gate import ConfirmGateMiddleware  # noqa: E402

tmp = tempfile.mkdtemp()
ap._AUDIT_PATH = os.path.join(tmp, "a.jsonl")

ok, fail = 0, []
def T(name, cond):
    global ok
    if cond: ok += 1
    else: fail.append(name); print("  FAIL", name)

with patch.object(ConfirmGateMiddleware, "_level", staticmethod(lambda: "strict")):
    g = ConfirmGateC1()
    with patch.object(ConfirmGateC1, "_tid", staticmethod(lambda: "hooktest")):
        TC = {"name": "execute", "args": {"command": "ls"}, "id": "t1", "type": "tool_call"}
        CFG = {"allowed_decisions": ["approve", "edit", "reject"]}
        # approve：原样返回
        tc_out, msg_out = g._process_decision({"type": "approve"}, dict(TC), CFG)
        T("approve 原样放行", tc_out is not None and msg_out is None)
        # edit：换参生效
        tc2, _ = g._process_decision(
            {"type": "edit", "edited_action": {"name": "execute", "args": {"command": "pwd"}}},
            dict(TC), CFG)
        T("edit 改参不扰", tc2["args"]["command"] == "pwd")
        # reject：出 error ToolMessage（官方件 reject 分支要 allowed_decisions 配置）
        # reject：1.3.18 实测=TC 保留+追加 error ToolMessage（执行过滤在路由层，
        # Nova 卷"顺手实证"段与签名段自相矛盾，以本件实测为准——版本钉的价值）
        tc3, msg3 = g._process_decision({"type": "reject", "message": "不行"}, dict(TC), CFG)
        T("reject 语义保留（TC 留+消息追）", tc3 is not None and msg3 is not None
          and "不行" in str(msg3.content))

lines = [json.loads(l) for l in open(ap._AUDIT_PATH, encoding="utf-8")]
c1 = [r for r in lines if r.get("ev") == "c1_decision"]
T("三 decision 全落账", len(c1) == 3)
T("账带 tid/tool/dtype", all(r.get("tid") == "hooktest" and r.get("tool") == "execute"
                             and r.get("dtype") in ("approve", "edit", "reject") for r in c1))
T("edit 标记在账", any(r.get("edited") for r in c1))
print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
sys.exit(1 if fail else 0)
