"""围炉/圆桌共用件（r39，四家 R37 审查合批抽公共层）：
模型调用安全层（空返回/截断/审核静默的统一兜底）+ 原子落盘 + 设置读取。
两图共享同款行为，占位语义/重试纪律只维护一份。
"""
import json
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

BASE = Path(__file__).resolve().parent

PLACEHOLDER = "rt_placeholder"  # additional_kwargs 标记：沉默占位不算观点


def load_settings() -> dict:
    """读 settings.json；失败打警告不静默——fallback 生效要让管理员看得见（Eve 新炮4：
    配置缺失要么响要么死，静默吞成 {} 会让 fallback 模型顶替配置悄悄干活）。"""
    try:
        return json.loads((BASE / "settings.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[chat_kit] settings.json 读取失败（{type(e).__name__}），本节点退回硬编码默认",
              file=sys.stderr, flush=True)
        return {}


def text_of(msg_obj) -> str:
    """取正文字面：content 支持 str/多段 list；content 全空而 reasoning_content 有货时
    （书生系思考模型偶发）取思维链但显式标注——不标注会把思维链当发言混进哈希链
    （hy3 P2-6 与 NOVA P1-4 的折中：既不丢失也不冒充）。"""
    c = getattr(msg_obj, "content", "")
    if isinstance(c, list):
        c = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    c = str(c).strip()
    if not c:
        r = (getattr(msg_obj, "additional_kwargs", {}) or {}).get("reasoning_content")
        if r and str(r).strip():
            return f"（思维链节选，非正式发言）{str(r).strip()[:400]}"
    return c


def ask(model, msgs, retries: int = 2) -> tuple:
    """调模型取正文，返回 (text, complete)。
    - 空返回（审核静默）：追加提醒重试（09-11 活体实证书生随机吞声，多试显著降概率）
    - 有正文+finish_reason=length/content_filter：硬信号说明重试救不了（撞顶/内容被过滤），
      止损失血直接回（探针实证 max_tokens 生效下 length 连撞三次纯烧钱）
    - 端点不回 finish_reason（书生兼容层常见）：从宽当完成，宁漏不误伤——误伤=整场白重试
    - 网络/SDK 异常向上抛，由调用方兜占位。
    """
    best = ""
    for i in range(retries + 1):
        out = model.invoke(list(msgs))
        t = text_of(out)
        fr = (getattr(out, "response_metadata", {}) or {}).get("finish_reason") or ""
        if t and fr not in ("length", "content_filter"):
            return t, True
        if len(t) > len(best):
            best = t
        if t:
            return t, False
        msgs = list(msgs) + [HumanMessage("请把正文完整直出，别中断，别只回确认。")]
    return best, False


def placeholder_msg(name: str, text: str):
    """沉默占位消息：name 用 system 系（不冒充座位），打标不算观点（Eve 新炮6：
    占位是平台生成的，链上角色语义要诚实）。"""
    from langchain_core.messages import AIMessage

    return AIMessage(content=text, name=name,
                     additional_kwargs={PLACEHOLDER: True})


def atomic_write_text(path: Path, text: str) -> None:
    """tmp+rename 原子写（Eve 新炮3）：truncate-then-write 写一半崩溃会留半张皮，
    下游照读不误；notes 是圆桌的原料源，落盘必须原子。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
