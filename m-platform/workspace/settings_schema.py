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
    # r34（CB 1.4）：uiZoom 登记入 schema 单源（此前 InterfaceTab 假默认 110、
    # page.tsx ?? 100 双源漂移；实际值 100）
    "interface.uiZoom":             {"default": 100, "type": "int", "ui": "界面", "note": "浏览器缩放百分比（90-160）"},
    # —— 通用/安全 ——
    "general.confirmLevel":        {"default": "strict", "type": "enum", "ui": "通用", "note": "四档确认门 plan<strict<auto_edit<full；非法/缺=fail-closed strict；r32（09-26 爸爸裁决）：四档自由直切，个人平台不设密码门，等多用户版再议"},
    "general.admin_name":          {"default": "admin", "type": "str", "ui": "管理", "note": "登录名（09-17 双要素）"},
    # —— 模型运行参数（批⑤新收口） ——
    "model.maxRetries":            {"default": 3, "type": "int", "ui": "模型", "note": "ChatOpenAI 自动重试（429/慢响应）"},
    "model.requestTimeout":        {"default": 90, "type": "int", "ui": "模型", "note": "单次请求超时秒"},
    "models.contextLimits":        {"default": {"glm-4.5-air": 131072, "glm-4.6v": 65536}, "type": "dict", "ui": "模型", "note": "模型名→窗口（覆盖默认表）。glm-4.7 条目已删（09-04 出局模型的历史残留，爸爸 09-27 发现）"},
    # —— 后台任务模型（W5：界面→任务模型可选） ——
    "task.model":                  {"default": "", "type": "str", "ui": "界面", "note": "后台任务（标题生成等）用哪个具体模型；留空=沿用原有回退链（scribe→boss），与旧行为兼容"},
    # —— RAG/嵌入 ——
    "rag.embeddingModel":          {"default": "qwen3-embedding:0.6b", "type": "str", "ui": "文档", "note": "嵌入模型唯一真源"},
    "rag.embeddingDim":            {"default": 1024, "type": "int", "ui": "文档", "note": "向量维度；换模型改此值+重建全库"},
    # —— 搜索端点（批②收口，公网引擎只许 https） ——
    "search.engine":               {"default": "auto", "type": "str", "ui": "联网搜索", "note": "auto=按可用钥匙选"},
    "search.searxngLang":            {"default": "all", "type": "str", "ui": "联网搜索", "note": "SearXNG 语言档（r35 Qoder P2-19 登记，此前后端/WebTab 双源字面量）"},
    "search.resultCount":          {"default": 5, "type": "int", "ui": "联网搜索", "note": "结果条数"},
    "search.searxngUrl":           {"default": "http://searxng:8080/search", "type": "str", "ui": "联网搜索", "note": "容器内网地址（scheme 轻闸门）"},
    "search.bochaUrl":             {"default": "https://api.bochaai.com/v1/web-search", "type": "str", "ui": "联网搜索", "note": "公网引擎 https-only"},
    "search.tavilyUrl":            {"default": "https://api.tavily.com/search", "type": "str", "ui": "联网搜索", "note": "同上"},
    "search.metasoUrl":            {"default": "https://metaso.cn/api/mcp", "type": "str", "ui": "联网搜索", "note": "同上"},
    # —— 图像 ——
    "images.sdUrl":                {"default": "http://host.docker.internal:7860", "type": "str", "ui": "图片", "note": "容器视角（09-17 修正语义）"},
    # —— 工作区分区（r36 09-27 爸令：容器与宿主机明确分开，如 ZCode 的工作区概念） ——
    "workspace.containerRoot":       {"default": "mia_home", "type": "str", "ui": "管理", "note": "容器工作区根（相对 workspace 的目录）——米娅与牛马的文件/执行域边界；改后重启容器生效"},
    "workspace.hostNote":            {"default": "", "type": "str", "ui": "管理", "note": "宿主执行域（完全访问档经 host_runner 到达，起点由宿主 .env 的 MIA_HOST_RUNNER_CWD 控制，默认 D:\\m）——此键仅存说明，不控制行为"},
    # —— 对话压缩（r35 Qoder P1-7/P1-8：graph.py _compaction_middleware 真消费，此前整节未登记=验收官全盲） ——
    "interface.compaction.enabled":   {"default": True, "type": "bool", "ui": "界面", "note": "关掉=不挂压缩中间件"},
    "interface.compaction.threshold": {"default": "", "type": "str", "ui": "界面", "note": "触发阈值 token；留空=deepagents 官方默认（前端不许再假显 80000）"},
    "interface.compaction.cap":       {"default": "", "type": "str", "ui": "界面", "note": "阈值上限；留空=官方默认"},
    "interface.compaction.retained":  {"default": "", "type": "str", "ui": "界面", "note": "保留条数；留空=官方默认"},
    "interface.compaction.prompt":    {"default": "", "type": "str", "ui": "界面", "note": "自定义压缩提示词；留空=官方默认"},
    "interface.compaction.provider":  {"default": "", "type": "str", "ui": "界面", "note": "压缩模型服务商（与 model 成对）；留空=boss"},
    "interface.compaction.model":     {"default": "", "type": "str", "ui": "界面", "note": "压缩模型；配便宜档不烧大模型（R69）"},
    # —— 模型参数（r36n 09-28 爸令实数化：显示值=生效值，出处=Qwen3.8 官方推荐） ——
    "general.params.temperature":    {"default": 1.0, "type": "float", "ui": "模型", "note": "采样温度；1.0=千问官方思考模式推荐值（qwen.ai 评测口径 temp=1.0/top_p=0.95），留空也按此显式传给模型"},
    "general.params.max_tokens":     {"default": 32768, "type": "int", "ui": "模型", "note": "全局兜底输出上限（09-28 爸令：给满≠锁死——此值只是查不到 per-model 表时的保守兜底，别拿它焊死平台）"},
    # —— 权限开关（r35 Qoder P2-14/P1-7：tools.py 真消费，miaManageEmail 此前前端零入口=死路文案） ——
    "permissions.miaManageAgents":    {"default": True, "type": "bool", "ui": "管理", "note": "关=米娅不能增删改牛马"},
    "permissions.miaManageEmail":     {"default": True, "type": "bool", "ui": "管理", "note": "关=米娅不能管理邮箱（r35 补 GeneralTab 开关入口）"},
    # —— 人设（前端 GeneralTab 真渲染，此前未登记） ——
    "general.system_prompt":          {"default": "", "type": "str", "ui": "通用", "note": "米娅人设/系统提示词追加段"},
    # —— 书记员/记忆（批⑤新收口） ——
    "scribe.extractThreshold":     {"default": 600, "type": "int", "ui": "管理", "note": "累积字数触发事实抽取"},
    "scribe.agingDays":            {"default": 30, "type": "int", "ui": "管理", "note": "笔记 aging 巡检阈值（天）"},
    # —— 外部岗/审批（批⑤新收口） ——
    "approvals.claimTimeout":      {"default": 1800, "type": "int", "ui": "牛马矩阵", "note": "外部岗领取超时秒（09-17 深夜知夏拍板归类）"},
    # —— CodeBuddy 网关（批⑤新收口） ——
    "codebuddy.defaultModel":      {"default": "Qwen/Qwen3.8-Flash-Next", "type": "str", "ui": "牛马矩阵", "note": "配置>env CODEBUDDY_MODEL>默认（09-17 深夜知夏拍板归类）"},
    "codebuddy.allowedModels":     {"default": "", "type": "str", "ui": "牛马矩阵", "note": "米娅按需换模型的白名单（逗号分隔）；defaultModel 恒在名单内；env 可整体压过"},
    # —— 围炉/圆桌座位（既有键登记入表） ——
    "hearth.A":                    {"default": {}, "type": "dict", "ui": "牛马矩阵", "note": "{provider,model} 双必填（09-17 fail-closed）"},
    "hearth.B":                    {"default": {}, "type": "dict", "ui": "牛马矩阵", "note": "同上"},
    "roundtable.A":                {"default": {}, "type": "dict", "ui": "牛马矩阵", "note": "同上"},
    "roundtable.B":                {"default": {}, "type": "dict", "ui": "牛马矩阵", "note": "同上"},
    "roundtable.host":             {"default": {}, "type": "dict", "ui": "牛马矩阵", "note": "未配回退 boss（有意设计）"},
}


def schema_json() -> dict:
    return {k: {kk: vv for kk, vv in v.items()} for k, v in SCHEMA.items()}


def default_of(path: str, sentinel=None):
    """消费点统一入口：取键默认值（settings 合并由 settings_mgr 做，这里只供 schema 侧）。"""
    return SCHEMA.get(path, {}).get("default", sentinel)
