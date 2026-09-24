# -*- coding: utf-8 -*-
"""edit_memory 记忆变更落账回归测（G-5，09-16 fix4，Cora MemSecBench 线索催生）。

mock 边界（零活体声明）：
- _BASE() 顶替 → tmp 目录（绝不碰真 mia_home/memory）
- _STORE 顶替 → MagicMock（**测本体绝不写真 PG 镜像**，只验"调没调"；
  注：import mia_agent.tools 会触发 store.py 模块级 _make_store() 连库，属既有模块设计，非本测新增活体）
- approvals._audit 顶替 → 内存记账哨兵（真通道只在第 4 组出现，且 _AUDIT_PATH 重定向 tmp）
断言面：成功写→恰一条 ev=memory_change（五字段+ts 通道自带）；字段值正确；
**脱敏**（明文内容绝不进账，家规）；_audit 抛→写入主链不受影响但 print 出声；
read/去重命中=没写就不落账。
"""
import hashlib
import io
import json
import contextlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import approvals as appr  # noqa: E402
import mia_agent.tools as mt  # noqa: E402

ok, fail = 0, []
CELLS = []


def T(name, cond):
    global ok
    if cond:
        ok += 1
        CELLS.append(name)
        print("  ok", name)
    else:
        fail.append(name)
        print("  FAIL", name)


SECRET = "血泪明文标记-7q2Z 这串字绝不该出现在批准账里"
FIELDS = ("action", "section", "project", "content_len", "content_sha16")


def sha16(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def run_edit(tmp, args, store=None, audit_sink=None, audit_boom=False):
    """在 mock 面跑一次 edit_memory，返回 (结果串, stdout, 账列表)。"""
    recs = audit_sink if audit_sink is not None else []

    def _spy(ev, **kw):
        if audit_boom:
            raise RuntimeError("mock 账本炸")
        recs.append({"ev": ev, **kw})

    buf = io.StringIO()
    with patch.object(mt, "_BASE", lambda: tmp), \
         patch.object(mt, "_STORE", store if store is not None else MagicMock()), \
         patch.object(appr, "_audit", _spy):
        with contextlib.redirect_stdout(buf):
            res = mt.edit_memory.func(*args)
    return res, buf.getvalue(), recs


# ── 1. 正例：append 成功写 → 账落且脱敏 ──
tmp1 = Path(tempfile.mkdtemp(prefix="zmem_"))
store1 = MagicMock()
res1, out1, recs1 = run_edit(tmp1, ("append", "测试区", SECRET, "fix4proj"), store=store1)
T("1.1 append 成功：返回 ✅ 且正文落盘（备份件在）",
  "✅ 记忆已更新" in res1
  and SECRET in (tmp1 / "mia_home" / "memory" / "projects" / "fix4proj.md").read_text(encoding="utf-8")
  and (tmp1 / "mia_home" / "memory" / "projects" / "fix4proj.md.bak").exists())
T("1.2 PG 镜像同路写入被调（namespace 为项目分区）",
  store1.put.called and store1.put.call_args[0][0] == ("memories", "projects", "fix4proj"))
T("1.3 恰落一条账，ev=memory_change",
  len(recs1) == 1 and recs1[0]["ev"] == "memory_change")
T("1.4 五字段齐全且值正确（action/section/project/content_len）",
  all(k in recs1[0] for k in FIELDS)
  and recs1[0]["action"] == "append" and recs1[0]["section"] == "测试区"
  and recs1[0]["project"] == "fix4proj" and recs1[0]["content_len"] == len(SECRET))
T("1.5 content_sha16=sha256 前 16 位（可事后比对不可还原）", recs1[0]["content_sha16"] == sha16(SECRET))
_blob1 = json.dumps(recs1, ensure_ascii=False)
T("1.6 脱敏铁律：账里不含明文子串、除 len/sha16 外无 content 类字段",
  SECRET not in _blob1
  and not any("content" in k for k in recs1[0] if k not in ("content_len", "content_sha16")))

# ── 2. 反例：_audit 抛 → 写入主链不受影响 + print 出声 ──
tmp2 = Path(tempfile.mkdtemp(prefix="zmem_"))
res2, out2, recs2 = run_edit(tmp2, ("append", "测试区", SECRET), audit_boom=True)
T("2.1 落账炸了写入仍成功（返回 ✅、文件已写）",
  "✅ 记忆已更新" in res2 and SECRET in
  (tmp2 / "mia_home" / "memory" / "MEMORY.md").read_text(encoding="utf-8"))
T("2.2 出声不静默（stdout 含审计落账失败）",
  "审计落账失败" in out2 and len(recs2) == 0)

# ── 3. 没写=不落账（read / 去重命中） ──
tmp3 = Path(tempfile.mkdtemp(prefix="zmem_"))
res3a, _, recs3a = run_edit(tmp3, ("read", "测试区"))
T("3.1 read 只读不落账", "✅" not in res3a and len(recs3a) == 0)
res3b, _, recs3b = run_edit(tmp3, ("append", "测试区", SECRET))
T("3.2 首次 append 落一条账", len(recs3b) == 1)
recs3c = []
res3c, _, _ = run_edit(tmp3, ("append", "测试区", SECRET), audit_sink=recs3c)
T("3.3 去重命中（未写入）不落账", "已存在" in res3c and len(recs3c) == 0)

# ── 4. 真通道：走 approvals._audit 本体（_AUDIT_PATH 重定向 tmp），ts 由通道自带 ──
tmp4 = Path(tempfile.mkdtemp(prefix="zmem_"))
ledger = tmp4 / "approvals_log.jsonl"
# 预置一个有内容的小节，好让 archive 走"真变更"分支（archive 不带 content，len=0）
_seed = tmp4 / "mia_home" / "memory"
_seed.mkdir(parents=True)
(_seed / "MEMORY.md").write_text("# 米娅的记忆\n\n## 测试区\n- 旧事一条\n", encoding="utf-8")
buf4 = io.StringIO()
with patch.object(mt, "_BASE", lambda: tmp4), patch.object(mt, "_STORE", MagicMock()), \
     patch.object(appr, "_AUDIT_PATH", str(ledger)):
    with contextlib.redirect_stdout(buf4):
        res4 = mt.edit_memory.func("archive", "测试区")
lines4 = ledger.read_text(encoding="utf-8").strip().splitlines() if ledger.exists() else []
rec4 = json.loads(lines4[-1]) if lines4 else {}
T("4.1 真通道落账一条（archive 也算变更：整节搬家内容未变但账要记），ts 随通道入账",
  "✅ 记忆已更新" in res4 and len(lines4) == 1
  and rec4.get("ev") == "memory_change" and "ts" in rec4
  and rec4.get("action") == "archive" and rec4.get("content_len") == 0)
T("4.2 真账本原文不含明文（jsonl 逐字节核对，含被归档小节的正文）",
  bool(lines4) and "旧事一条" not in lines4[-1] and SECRET not in lines4[-1])

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
print("格单：" + " | ".join(f"{i+1}. {c}" for i, c in enumerate(CELLS)))
raise SystemExit(1 if fail else 0)
