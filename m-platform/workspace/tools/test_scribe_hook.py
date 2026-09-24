# -*- coding: utf-8 -*-
"""scribe_hook 书记员中间件行为测（09-15 盲区补测一期）。

此前状态：WIKI 注记"仅源码文本断言、无行为测"。本件直接喂 wrap_model_call /
wrap_tool_call / build_card_inject 断行为：
- R64 强制令走 system 侧注入（动手前查笔记字样进 system_prompt）
- r2-1 钉：工具结果面零污染（REMINDER 不拼进返回值）
- enabled=false 整体禁用（不注入、不记 auto_log）
- 记账异常吞落不阻断主链（_log 炸、结果照样回）
- build_card_inject §3.1 注入形状：目录行、prov 门、facts/MEMORY/隐藏/备份不列、
  60 字符硬截、2KB 截尾、缺目录空串
零活体：root=tmpdir；默认不触后台模型线程——第 7 组以假 providers/settings_mgr 顶替，
同步直调 _extract_facts 显式跑一次抽取，验"抽取旁路补落 memory_change 账 + 明文绝不进账"，仍零活体。
"""
import asyncio
import hashlib
import io
import json
import sys
import tempfile
import types
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import scribe_hook as sh  # noqa: E402
import approvals as appr  # noqa: E402

ok, fail = 0, []
CELLS = []

def T(name, cond):
    global ok
    if cond:
        ok += 1
        CELLS.append(name)
    else:
        fail.append(name)
        print("  FAIL", name)


def settings(enabled=True):
    return lambda: {"scribe": {"enabled": enabled, "factExtract": False}}


class Req:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def mk_mw(tmp):
    return sh.ScribeMiddleware(tmp)


RES = SimpleNamespace(content="结果文本-不含提醒尾巴")

# ── 1. wrap_model_call：工作规范强制注入 system 侧 ──
tmp = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw = mk_mw(tmp)
req = Req(system_prompt="你是米娅")
with patch.object(sh, "load_settings", settings(True)):
    out = mw.wrap_model_call(req, lambda r: RES)
T("1 注入含【本轮工作规范】", "【本轮工作规范" in req.system_prompt)
T("1 注入含动手前查笔记令", "动手前先查笔记" in req.system_prompt)
T("1 注入含绝对红线（银行支付禁碰）", "银行" in req.system_prompt and "禁碰" in req.system_prompt)
T("1 原 prompt 保留在前", req.system_prompt.startswith("你是米娅"))
T("1 handler 结果原样透传", out is RES)

# ── 2. enabled=false 全禁 ──
tmp2 = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw2 = mk_mw(tmp2)
req2 = Req(system_prompt="SP")
with patch.object(sh, "load_settings", settings(False)):
    mw2.wrap_model_call(req2, lambda r: RES)
T("2 禁用时不注入", req2.system_prompt == "SP")
req3 = Req(system_prompt="SP", tool_call={"name": "execute", "args": {"command": "ls"}})
with patch.object(sh, "load_settings", settings(False)):
    out3 = mw2.wrap_tool_call(req3, lambda r: RES)
T("2 禁用时工具链透传", out3 is RES)
T("2 禁用时不落 auto_log", not (tmp2 / "notes" / "auto_log.md").exists())

# ── 3. wrap_tool_call：随手记落 auto_log ──
tmp3 = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw3 = mk_mw(tmp3)
req4 = Req(system_prompt="SP", tool_call={"name": "execute", "args": {"command": "python x.py"}})
with patch.object(sh, "load_settings", settings(True)):
    out4 = mw3.wrap_tool_call(req4, lambda r: RES)
T("3 结果原样返回（不被钩子改写）", out4 is RES)
log = tmp3 / "notes" / "auto_log.md"
T("3 auto_log 落盘", log.is_file())
txt = log.read_text(encoding="utf-8")
T("3 记录含工具名", "**execute**" in txt)
T("3 记录含参数摘要", "python x.py" in txt)
T("3 记录含结果摘要行", "结果文本" in txt)
T("3 r2-1 钉：工具结果面零污染", "工作规范" not in str(getattr(out4, "content", "")))

# 异步版同逻辑
tmp4 = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw4 = mk_mw(tmp4)


async def _ahandler(r):
    return RES


req5 = Req(system_prompt="SP", tool_call={"name": "read_file", "args": {"file_path": "a.md"}})
with patch.object(sh, "load_settings", settings(True)):
    out5 = asyncio.run(mw4.awrap_tool_call(req5, _ahandler))
T("3b async 结果透传", out5 is RES)
T("3b async 落 auto_log",
  "**read_file**" in (tmp4 / "notes" / "auto_log.md").read_text(encoding="utf-8"))

# ── 4. 钩子异常吞落不阻断主链 ──
tmp5 = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw5 = mk_mw(tmp5)


def _boom(*a, **k):
    raise RuntimeError("mock 记账炸")


mw5._log = _boom
req6 = Req(system_prompt="SP", tool_call={"name": "execute", "args": {}})
with patch.object(sh, "load_settings", settings(True)):
    try:
        out6 = mw5.wrap_tool_call(req6, lambda r: RES)
        survived = out6 is RES
    except Exception:
        survived = False
T("4 _log 炸仍正常返回结果", survived)


# 真通道版：root 置坏 → _aging_report 内部 TypeError → 其自带 try/except 自吞 →
# 主链照常返回（aging 是钩子内部件，不测被 patch 顶包后的假炸）
tmp7 = Path(tempfile.mkdtemp(prefix="zscribe_"))
mw7 = mk_mw(tmp7)
mw7._root = None
with patch.object(sh, "load_settings", settings(True)):
    try:
        out6b = mw7.wrap_tool_call(Req(system_prompt="SP",
                                       tool_call={"name": "x", "args": {}}),
                                   lambda r: RES)
        survived_b = out6b is RES
    except Exception:
        survived_b = False
T("4b aging 内部炸自吞不阻断主链", survived_b)
# _aging_report 本体：notes 不存在直接返回，不炸
mw_fresh = mk_mw(Path(tempfile.mkdtemp(prefix="zscribe_")))
try:
    mw_fresh._aging_report()
    T("4c notes 缺失 aging 不炸", True)
except Exception:
    T("4c notes 缺失 aging 不炸", False)

# ── 5. build_card_inject 注入形状（§3.1 + G-3） ──
mem = Path(tempfile.mkdtemp(prefix="zscribe_mem_"))
(mem / "b_self.md").write_text("# B标题\n正文一大段\n", encoding="utf-8")
(mem / "a_notitle.md").write_text("没有标题的卡\n", encoding="utf-8")
(mem / "c_delegated.md").write_text("---\nprov: delegated\n---\n# 外派回帖\n", encoding="utf-8")
(mem / "d_inbox.md").write_text("---\nprov: inbox\n---\n# 信箱\n", encoding="utf-8")
(mem / "e_ok.md").write_text("---\nprov: self\n---\n# 晋升卡\n", encoding="utf-8")
(mem / "facts-2026-09.md").write_text("# 流水\n", encoding="utf-8")
(mem / "MEMORY.md").write_text("# 索引\n", encoding="utf-8")
(mem / ".reflect_last").write_text("x", encoding="utf-8")
(mem / "old.md.bak").write_text("# 备份\n", encoding="utf-8")
(mem / "nag-01.md").write_text("# 催办\n", encoding="utf-8")
inj = sh.build_card_inject(mem)
lines = [l for l in inj.splitlines() if l.startswith("- ")]
T("5 前导双换行", inj.startswith("\n\n"))
T("5 self 卡出目录行", "- [memory:b_self.md] B标题" in inj)
T("5 无标题回落文件名", "- [memory:a_notitle.md] a_notitle.md" in inj)
T("5 按文件名升序=确定性", [l.split("memory:")[1].split("]")[0] for l in lines]
  == sorted(l.split("memory:")[1].split("]")[0] for l in lines))
T("5 G-3：delegated 连目录行都不出", "c_delegated" not in inj)
T("5 G-3：inbox 连目录行都不出", "d_inbox" not in inj)
T("5 prov:self 显式晋升可注入", "e_ok.md" in inj)
T("5 facts 流水不注入", "facts-" not in inj)
T("5 MEMORY.md 不注入", "MEMORY" not in inj)
T("5 隐藏件不注入", ".reflect" not in inj)
T("5 备份件不注入", ".bak" not in inj)
T("5 nag 提醒件不注入", "nag-" not in inj)
T("5 正文永不注入", "正文一大段" not in inj)

# 60 字符硬截
mem2 = Path(tempfile.mkdtemp(prefix="zscribe_mem2_"))
(mem2 / "long.md").write_text("# " + "长" * 100 + "\n", encoding="utf-8")
inj2 = sh.build_card_inject(mem2)
l2 = inj2.splitlines()[-1]
T("5 目录行 ≤60 字符", len(l2) <= 60 and l2.startswith("- [memory:long.md]"))

# 2KB 总量截尾
mem3 = Path(tempfile.mkdtemp(prefix="zscribe_mem3_"))
for i in range(300):
    (mem3 / f"card{i:03d}.md").write_text(f"# 卡{i}标题占位内容较长较长\n", encoding="utf-8")
inj3 = sh.build_card_inject(mem3)
T("5 超限截尾带标记", inj3.rstrip().endswith("...(目录截断)"))
T("5 截断后总量 ≤2KB+标记", len(inj3.encode("utf-8")) <= sh._CARD_TOC_LIMIT)
T("5 截断仍保序且含首卡", "- [memory:card000.md]" in inj3)

T("5 缺目录回空串（是门不是故障源）", sh.build_card_inject(mem / "no_such") == "")
T("5 空目录回空串", sh.build_card_inject(Path(tempfile.mkdtemp())) == "")

# ── 6. prov_of_card 缺省语义 ──
T("6 无 frontmatter=self", sh.prov_of_card("# 普通卡") == "self")
T("6 有 fm 无 prov 键=self", sh.prov_of_card("---\ntags: x\n---\n# a") == "self")
T("6 prov 空值=self", sh.prov_of_card("---\nprov:\n---\n# a") == "self")
T("6 prov 带引号解析", sh.prov_of_card("---\nprov: \"inbox\"\n---\n# a") == "inbox")
T("6 未闭合 fm 也能找 prov", sh.prov_of_card("---\nprov: delegated\n# 忘了闭合") == "delegated")

# ── 7. R51 事实抽取旁路补账（09-16 fix5，Veda P1①：抽取通道直写 memory/facts-*.md 曾绕过 memory_change 审计）──
# 零活体：假 providers/settings_mgr 顶替模型与配置，_extract_facts 同步直调（不启后台线程、不连真模型服务）。
FACT_PLAIN = "爸爸银行卡尾号明文标记 8837-K9qZ 这条抽取事实正文绝不能进批准账"
FACT_PLAIN_2 = "证件号明文标记 3301-ABcd-8899 这条只该活在 memory 绝不进 jsonl 账本"


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeChat:
    def __init__(self, content):
        self._c = content

    def invoke(self, prompt):
        return _Resp(self._c)


def _fake_ext_mods(content):
    prov = types.ModuleType("providers")
    prov.make_model = lambda provider="", model="", **k: _FakeChat(content)
    smgr = types.ModuleType("settings_mgr")
    smgr.load_agents_config = lambda: {"archivist": {"provider": "p", "model": "m"}}
    return {"providers": prov, "settings_mgr": smgr}


def _facts_written(root):
    hits = list((root / "memory").glob("facts-*.md"))
    return hits[0] if hits else None


def sha16(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# 7.1 抽取成功→facts 明文落 memory 文件 + 恰一条 ev=memory_change/action=extract 落账（字段值全对）
tmp8 = Path(tempfile.mkdtemp(prefix="zscribe_ext_"))
mw8 = sh.ScribeMiddleware(tmp8)
_sink7 = []


def _spy_audit(ev, **kw):
    _sink7.append({"ev": ev, **kw})


with patch.dict(sys.modules, _fake_ext_mods(FACT_PLAIN)), patch.object(appr, "_audit", _spy_audit):
    mw8._extract_facts("对话片段素材（事实正文由假模型给出，与素材无关）")
_fact8 = _facts_written(tmp8)
_body8 = _fact8.read_text(encoding="utf-8") if _fact8 else ""
_chg8 = _body8.rstrip("\n")
T("7.1 抽取成功：facts 明文写入 memory 文件（主链照旧）", bool(_fact8) and FACT_PLAIN in _body8)
T("7.2 旁路补账：恰一条 ev=memory_change/action=extract，file=相对路径、len/sha16 值正确",
  len(_sink7) == 1 and _sink7[0]["ev"] == "memory_change" and _sink7[0]["action"] == "extract"
  and _sink7[0]["file"].startswith("memory/facts-") and _sink7[0]["file"].endswith(".md")
  and _sink7[0]["content_len"] == len(_chg8) and _sink7[0]["content_sha16"] == sha16(_chg8))
# 7.3 脱敏铁律（spy 账目）：账 json 逐字不含 facts 明文子串、除 len/sha16 外无 content 类字段
_blob7 = json.dumps(_sink7, ensure_ascii=False)
T("7.3 脱敏：spy 账目不落 facts 明文子串、无裸 content 字段",
  FACT_PLAIN not in _blob7
  and not any("content" in k for k in _sink7[0] if k not in ("content_len", "content_sha16")))
# 7.4 真通道逐字节（走 approvals._audit 本体，_AUDIT_PATH 重定向 tmp jsonl）：实账不含明文、memory 却有
tmp9 = Path(tempfile.mkdtemp(prefix="zscribe_ext_"))
mw9 = sh.ScribeMiddleware(tmp9)
_ledger9 = tmp9 / "approvals_log.jsonl"
with patch.dict(sys.modules, _fake_ext_mods(FACT_PLAIN_2)), patch.object(appr, "_AUDIT_PATH", str(_ledger9)):
    mw9._extract_facts("素材")
_lines9 = _ledger9.read_text(encoding="utf-8").splitlines() if _ledger9.exists() else []
_fact9 = _facts_written(tmp9)
T("7.4 真通道逐字节：账本单条 extract、ts 随通道入账、明文绝不进 jsonl；memory 文件确有明文",
  len(_lines9) == 1 and "memory_change" in _lines9[0] and '"extract"' in _lines9[0]
  and '"ts"' in _lines9[0] and FACT_PLAIN_2 not in _lines9[0]
  and bool(_fact9) and FACT_PLAIN_2 in _fact9.read_text(encoding="utf-8"))
# 7.5 落账炸→facts 仍写 + stdout 出声"审计落账失败" + 不抛回主链（工单要求 try 包住失败不挡抽取）
tmp10 = Path(tempfile.mkdtemp(prefix="zscribe_ext_"))
mw10 = sh.ScribeMiddleware(tmp10)


def _boom_audit(ev, **kw):
    raise RuntimeError("mock 账本炸")


_buf10 = io.StringIO()
with patch.dict(sys.modules, _fake_ext_mods(FACT_PLAIN)), patch.object(appr, "_audit", _boom_audit):
    with redirect_stdout(_buf10):
        mw10._extract_facts("素材")  # 落账炸但主链不应抛出
_fact10 = _facts_written(tmp10)
T("7.5 落账炸：facts 仍落盘 + stdout 出声'审计落账失败' + 不抛回抽取主链",
  bool(_fact10) and FACT_PLAIN in _fact10.read_text(encoding="utf-8")
  and "审计落账失败" in _buf10.getvalue())

print(f"\nRESULT: {ok} pass / {len(fail)} fail", fail if fail else "")
print("格单：" + " | ".join(f"{i+1}. {c}" for i, c in enumerate(CELLS)))
sys.exit(1 if fail else 0)
