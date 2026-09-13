# -*- coding: utf-8 -*-
"""remember_rules —— "批准并记住这类"规则表（爸爸 09-13 拍板开码）。

设计（四护栏，爸爸选定方案）：
  1. 精确规则：规则=(tool, key)——key=工具的关键参数规范化（写类=file_path，
     execute=command 去空白小写）；**永不支持通配/全工具放行**。
  2. 设置页可见可删：规则存 settings.remember_rules，走 settings 端点（token 门内），
     米娅无权增删（token 是爸爸权柄）。
  3. 命中全审计：gate 每次免卡放行写 approvals_log.jsonl（ev=rule_pass）。
  4. 语义=永久免卡：只给重复性安全动作用（如"写 notes/stats.md"日常统计），
     删/外发/派活类爸爸不该记（前端对高危工具隐藏此钮）。
"""
from __future__ import annotations

import re


def _norm_key(tool: str, args: dict) -> str:
    """从工具参数提取"这类"的键（规范化：去空白、小写、路径形态归一）。
    r49b：米娅文件工具的 file_path 绝对/相对双形态都指向同一文件（虚拟根），
    键必须归一（lstrip("/")），否则爸爸按绝对形态记的规则对相对形态调用不生效。"""
    a = args or {}
    if tool in ("write_file", "edit_file", "read_file", "delete", "delete_file"):
        p = str(a.get("file_path") or a.get("path") or "").strip().lower()
        return p.lstrip("/")
    if tool == "execute":
        cmd = str(a.get("command") or "")
        cmd = re.sub(r"\s+", " ", cmd).strip().lower()
        return cmd[:120]
    return ""


def rule_key(tool: str, args: dict) -> str:
    """对外：完整规则键（tool + ":" + key）。key 空=不可记（返回 ""）。"""
    k = _norm_key(tool, args)
    return f"{tool}:{k}" if k else ""


def hit(tool: str, args: dict, settings: dict) -> bool:
    """gate 查询：该调用是否命中"记住"规则。settings=load_settings() 结果。"""
    full = rule_key(tool, args)
    if not full:
        return False
    rules = (settings or {}).get("remember_rules") or []
    return any(str(r.get("key", "")).lower() == full for r in rules)
