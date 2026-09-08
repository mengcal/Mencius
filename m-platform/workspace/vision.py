"""
工作平台·识图直连接口
=====================================================================
为什么要直连：多模态直连识图快，但走 deepagents 管道（execute读文件+多层
编排）会超时(>150s)。所以识图单独走直连，绕过 deepagents。

【模型不硬编码（管理员铁律 2026-08-29）】识图模型完全由配置决定（唯一真源=设置页），优先级：
  1. 设置页 vision 节（settings.json: vision.provider / vision.model）
  2. 设置页 agents 节的 visual 工人岗（R65：不再读已废除的 agents_config.json）
  都没配 → 明确报错提示去设置页配，绝不偷偷指定某家模型。
  glm-5.3-flash / qwen3.8-flash / 智谱4.6v / 书生……只要配置里写了就能用。

用法（POST /vision）：
  {"image_path": "/home/user/workplatform/test_vision.png",
   "question": "这张图里有什么？"}
  {"image_b64": "base64字符串", "question": "..."}
"""
import base64

from providers import make_model


def _vision_model():
    """按配置构造识图模型。运行时读（设置页改完即生效），不缓存不硬编码。"""
    # 1) 设置页 vision 节
    try:
        from settings_mgr import load_settings
        v = load_settings().get("vision", {}) or {}
        provider, model = v.get("provider", ""), v.get("model", "")
        if provider and model:
            return make_model(provider, model, temperature=0.2)
    except Exception:
        pass
    # 2) 设置页 agents 节的 visual 工人岗（Sub-agents 页可改，R65 起经 settings_mgr 读）
    try:
        from settings_mgr import load_agents_config
        cfg = load_agents_config()
        vis = cfg.get("visual", {}) or {}
        if vis.get("provider") and vis.get("model"):
            return make_model(vis["provider"], vis["model"], temperature=0.2)
    except Exception:
        pass
    raise RuntimeError(
        "识图模型未配置：请在设置页 → vision 节（或 Sub-agents → visual）"
        "指定服务商和模型。识别什么模型用哪个，由管理员决定。"
    )


def _read_b64(image_path: str) -> str:
    """读图片文件 → base64。
    路径白名单锁死数据目录 mia_home/（上传文件都落这），越界即 PermissionError——
    本端点永远读不到密钥卷与源码卷。"""
    from pathlib import Path
    base = Path(__file__).resolve().parent / "mia_home"
    p = Path(image_path).resolve()
    if not p.is_file() or base != p.parent and base not in p.parents:
        raise PermissionError("image_path 只允许数据目录 mia_home 下的文件（对话上传的图片在此），越界路径已拒绝")
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


def analyze_image(image_path: str = "", image_b64: str = "", question: str = "请描述这张图片的内容") -> str:
    """多模态识图。给文件路径 或 base64，返回分析文本。"""
    if image_b64:
        b64 = image_b64
    elif image_path:
        try:
            b64 = _read_b64(image_path)
        except PermissionError as e:
            return f"错误：{e}"  # R79：白名单拒绝回文本（200 带 error），不再炸 500
    else:
        return "错误：需要提供 image_path 或 image_b64"

    mime = "image/png"
    if image_path and image_path.lower().endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"

    try:
        resp = _vision_model().invoke([
            {"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]}
        ])
        return str(resp.content)
    except Exception as e:
        return f"识图报错: {type(e).__name__} {str(e)[:200]}"
