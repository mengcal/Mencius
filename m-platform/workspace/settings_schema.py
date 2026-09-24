# -*- coding: utf-8 -*-
"""settings_schema.py — M 平台配置总表（单一配置源首版，09-17 深夜，知夏）

蓝本=OWUI backend/open_webui/env.py：全部配置键在一个文件登记（路径/默认值/类型/所属设置页/说明）。
规矩（Lesson 68+hy4 三挑刺）：
- 代码要读配置=走本表 default（settings_mgr.load_settings 合并），不许各文件再写字面量；
- 默认值来源=09-17 22:3x 现网快照冻结（notes/config-snapshot-0917.md），非手抄；
- 消费者清单由 hardcode_scan.py 机械生成（验收官跑），不靠人肉；
- 命名随大众惯例 camelCase（爸爸 09-17 夜裁决：命名问大众不问爸爸）。
新增键=先在这里登记，再在 settings 消费点引用；GET /settings/schema 下发给前端与验收官。
"""

SCHEMA = {
    # —— 通用/安全 ——
    "general.confirmLevel":        {"default": "strict", "type": "enum", "ui": "通用", "note": "四档确认门；非法/缺=fail-closed strict；r29 焊档：放宽须走 /settings/confirm-level 验旧密码，通用通道已关"},
    "general.admin_name":          {"default": "admin", "type": "str", "ui": "米娅与安全", "note": "登录名（09-17 双要素）"},
    # —— 模型运行参数（批⑤新收口） ——
    "model.maxRetries":            {"default": 3, "type": "int", "ui": "模型", "note": "ChatOpenAI 自动重试（429/慢响应）"},
    "model.requestTimeout":        {"default": 90, "type": "int", "ui": "模型", "note": "单次请求超时秒"},
    "models.contextLimitDefault":  {"default": 131072, "type": "int", "ui": "模型", "note": "未知模型上下文窗口兜底"},
    "models.contextLimits":        {"default": {"glm-4.7": 200000, "glm-4.5-air": 131072, "glm-4.6v": 65536}, "type": "dict", "ui": "模型", "note": "模型名→窗口（覆盖默认表）"},
    # —— 后台任务模型（W5：界面→任务模型可选） ——
    "task.model":                  {"default": "", "type": "str", "ui": "界面", "note": "后台任务（标题生成等）用哪个具体模型；留空=沿用原有回退链（scribe→boss），与旧行为兼容"},
    # —— RAG/嵌入 ——
    "rag.embeddingModel":          {"default": "qwen3-embedding:0.6b", "type": "str", "ui": "文档", "note": "嵌入模型唯一真源"},
    "rag.embeddingDim":            {"default": 1024, "type": "int", "ui": "文档", "note": "向量维度；换模型改此值+重建全库"},
    # —— 搜索端点（批②收口，公网引擎只许 https） ——
    "search.engine":               {"default": "auto", "type": "str", "ui": "搜索", "note": "auto=按可用钥匙选"},
    "search.resultCount":          {"default": 5, "type": "int", "ui": "搜索", "note": "结果条数"},
    "search.searxngUrl":           {"default": "http://searxng:8080/search", "type": "str", "ui": "搜索", "note": "容器内网地址（scheme 轻闸门）"},
    "search.bochaUrl":             {"default": "https://api.bochaai.com/v1/web-search", "type": "str", "ui": "搜索", "note": "公网引擎 https-only"},
    "search.tavilyUrl":            {"default": "https://api.tavily.com/search", "type": "str", "ui": "搜索", "note": "同上"},
    "search.metasoUrl":            {"default": "https://metaso.cn/api/mcp", "type": "str", "ui": "搜索", "note": "同上"},
    "search.bingUrl":              {"default": "https://www.bing.com/search", "type": "str", "ui": "搜索", "note": "同上"},
    # —— 图像 ——
    "images.engine":               {"default": "sd-webui", "type": "enum", "ui": "图像", "note": "sd-webui|default"},
    "images.sdUrl":                {"default": "http://host.docker.internal:7860", "type": "str", "ui": "图像", "note": "容器视角（09-17 修正语义）"},
    # —— 书记员/记忆（批⑤新收口） ——
    "scribe.extractThreshold":     {"default": 600, "type": "int", "ui": "米娅与安全", "note": "累积字数触发事实抽取"},
    "scribe.agingDays":            {"default": 30, "type": "int", "ui": "米娅与安全", "note": "笔记 aging 巡检阈值（天）"},
    # —— 外部岗/审批（批⑤新收口） ——
    "approvals.claimTimeout":      {"default": 1800, "type": "int", "ui": "牛马矩阵", "note": "外部岗领取超时秒（09-17 深夜知夏拍板归类）"},
    # —— CodeBuddy 网关（批⑤新收口） ——
    "codebuddy.defaultModel":      {"default": "Qwen/Qwen3.8-Flash-Next", "type": "str", "ui": "牛马矩阵", "note": "配置>env CODEBUDDY_MODEL>默认（09-17 深夜知夏拍板归类）"},
    "codebuddy.allowedModels":     {"default": "", "type": "str", "ui": "牛马矩阵", "note": "米娅按需换模型的白名单（逗号分隔）；defaultModel 恒在名单内；env 可整体压过"},
    # —— 围炉/圆桌座位（既有键登记入表） ——
    "hearth.A":                    {"default": {}, "type": "dict", "ui": "围炉", "note": "{provider,model} 双必填（09-17 fail-closed）"},
    "hearth.B":                    {"default": {}, "type": "dict", "ui": "围炉", "note": "同上"},
    "roundtable.A":                {"default": {}, "type": "dict", "ui": "圆桌", "note": "同上"},
    "roundtable.B":                {"default": {}, "type": "dict", "ui": "圆桌", "note": "同上"},
    "roundtable.host":             {"default": {}, "type": "dict", "ui": "圆桌", "note": "未配回退 boss（有意设计）"},
}


def schema_json() -> dict:
    return {k: {kk: vv for kk, vv in v.items()} for k, v in SCHEMA.items()}


def default_of(path: str, sentinel=None):
    """消费点统一入口：取键默认值（settings 合并由 settings_mgr 做，这里只供 schema 侧）。"""
    return SCHEMA.get(path, {}).get("default", sentinel)
