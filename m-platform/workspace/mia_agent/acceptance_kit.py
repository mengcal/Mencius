# -*- coding: utf-8 -*-
"""acceptance_kit —— 层2 验收/简报公共件（09-12 夜，五家意见合流）。

一个引擎三处复用（Cora"三个需求一个件"）：
  A. task_brief 目标字段（bug2 重置判定挂它：目标变化=新任务）
  B. acceptance 验收字面量（W5 铁证：核对=代码动词，不过米娅的手）
  C. execute 作用域根/路径形态（Veda 治本炮：卡验收断言禁绝对形式）

铁律（全部来自基线实测/五家评审）：
  - 字面量必须从【任务原文】机械提取（from=task_literal），模型只确认不发明
    ——自我授权/自我验收同病（Cora-2/NOVA）。
  - 提不到关键字面量 → needs_clarification（fallback: ask，求助免费，
    别让米娅猜一个验收标准再自己满足它——W5 模糊版复发）。
  - 核对读的是【文件系统实测】对【任务原文提取】，双独立源交叉（Eve：
    单一源自我比对=自证=不算验收）。
"""
from __future__ import annotations

import re

# Windows/Unix 路径字面量：带盘符、绝对 / 段、或相对多段（notes/x.md 形态）
_WIN_PATH = re.compile(r"[A-Za-z]:[\\/][\w\\/.\-一-鿿]*[\w\\/.\-]")
_UNIX_PATH = re.compile(r"(?<![\w/])(?:/[\w.\-一-鿿]+){2,}")
_REL_PATH = re.compile(r"(?<![\w/\.])([\w.\-一-鿿]+/)+[\w.\-一-鿿]+\.[A-Za-z0-9]{1,6}")
_QUOTED = re.compile(r"[\"'“‘「『]([^\"'”’」』]{2,40})[\"'”’」』]")
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


_FORBID_PREV = re.compile(r"(不要|别|除了|而非|勿|参考|删掉|删除|删|去掉|移除|清除)[^。；;]{0,12}$")
_CONV_WORDS = re.compile(r"^(的?[^。；;]{0,6})?(改成|改为|换成|变成|替换为|更新为)")
_CONV_NEARBY = re.compile(r"[^。；;]{0,8}(改成|改为|换成|变成|替换为|更新为)")


def _role_of(task_text: str, start: int, end: int) -> str:
    """字面量角色标注（r43 hy4 Q3：禁止项/旧值反向变必过项的病）。机械规则：
    - 前邻窗口有"不要/别/除了/参考" → forbidden（本来不该动）
    - 后邻紧贴变换词（"TODO"改成）→ old-value（该消失）
    - 前邻有变换词（改成"已完成"）→ target（该出现）
    - 其余 → target（保守：拿不准就核对，宁严勿漏）"""
    prev = task_text[max(0, start - 20):start]
    nxt = task_text[end:end + 10]
    if _FORBID_PREV.search(prev):
        return "forbidden"
    if re.match(r"\s*(改成|改为|换成|变成|替换为|更新为)", nxt) or _CONV_WORDS.match(nxt.lstrip("」』”’ ")[:10]):
        return "old-value"
    if _CONV_NEARBY.search(prev[-10:]):
        return "target"
    return "target"


def extract_literals(task_text: str) -> dict:
    """从任务原文机械提取验收字面量（每条带 role）。返回：
    {paths: [(value, role)], quotes: [(value, role)], numbers: [...],
     needs_clarification: bool}
    needs_clarification=写类任务无任何字面量（验收无从谈起→问爸爸，别猜）。
    """
    paths = []
    for rx in (_WIN_PATH, _UNIX_PATH, _REL_PATH):
        for m in rx.finditer(task_text):
            p = m.group(0)
            if all(p != v for v, _ in paths):
                paths.append((p, _role_of(task_text, m.start(), m.end())))
    quotes = []
    for m in _QUOTED.finditer(task_text):
        q = m.group(1).strip()
        if q and all(q != v for v, _ in quotes):
            quotes.append((q, _role_of(task_text, m.start(1), m.end(1))))
    numbers = _NUM.findall(task_text)
    has_target = any(r == "target" for _, r in paths + quotes)
    return {"paths": paths, "quotes": quotes, "numbers": numbers,
            "needs_clarification": bool(_is_write_task(task_text) and not has_target)}


_WRITE_VERBS = ("写", "新建", "创建", "追加", "改", "修改", "复制", "删", "存", "保存到",
                "整理", "汇总", "做成", "生成")  # r42：Eve 两级完成标志的 L0 门槛——
# 纯读任务（ls/grep 即终态）不进 needs_clarification；判据=写动词或产物文件字面量，
# 两者皆无=读任务=产物是消息本身。


def _is_write_task(task_text: str) -> bool:
    return any(v in task_text for v in _WRITE_VERBS)


def check_path_form(command: str, data_root_note: str = "相对路径") -> list:
    """C 件：execute 命令的写操作路径形态断言（Veda 治本炮，只报不拦——
    一期观测+卡面提示，硬拦开关留给 PlanCheck 配置）。
    r46b（09-13 E4 实证）：mia_home 也是她常撞的绝对形式坑源，一并入榜。
    命中项：shell 命令里出现 /开头单斜杠数据路径（/notes/... /mia_home/... 形态，
    文件工具可用而 execute 不可用的坑源）。"""
    bad = []
    for m in re.finditer(r"(?<![\w])(/(?:notes|memory|knowledge|mia_home)[\w.\-/]*)", command):
        bad.append(m.group(1))
    return bad


def literal_diff(items: list, actual: str) -> list:
    """B 件：验收核对（纯代码，不过模型）。r43（hy4 Q3）按 role 过滤：
    - target：actual 里必须出现（数字类用词界匹配，防 30 in 300 假阴性）
    - old-value：actual 里必须不出现（反向断言——TODO 没清才 miss）
    - forbidden：不参与核对（它本就不该被写）
    items: [{"kind": "path"|"quote"|"number", "value": v, "role": r}]；缺 role 视同 target。
    返回未命中/违例清单（空=验收过）。
    """
    miss = []
    for it in items:
        v = it.get("value", "")
        role = it.get("role", "target")
        if not v or role == "forbidden":
            continue
        if role == "old-value":
            if v in actual:
                miss.append({**it, "why": "旧值未清除"})
            continue
        if it.get("kind") == "number":
            if not re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w.])", actual):
                miss.append({**it, "why": "数字未命中（词界）"})
        elif v not in actual:
            miss.append({**it, "why": "字面量未命中"})
    return miss
