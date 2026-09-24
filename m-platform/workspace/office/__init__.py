"""
office —— 米娅「工作平台·小全车间」服务包（由 D:\\m\\workspace\\office.py 拆分而来）
公共入口：from office.app import app
模块地图：
- office.core                纯函数/常量公共层（_secrets_dir/_ck/_rate_ok/_rotate_log/_token_audit/_presented_token/BASE/.env）
- office.app                 装配层（create_app/CORSMiddleware/api_token_guard/守卫名单/uvicorn 入口）
- office.routers.providers   /settings*、/providers*、/models/all、SSRF 闸门
- office.routers.rag         RAG 存储层 + 五个 /rag/* 端点（第三扇代理门 /rag/query）
- office.routers.gates       _BodyCap 中间件类 + /vision + /codebuddy（前两扇代理门）
- office.routers.tasks       TASKS 账本 + /tasks/dispatch|webhook|list + /files/save + /threads/title
- office.routers.token_admin /settings/token（注册首设/轮换/清除）+ /auth/*（登录/改密）
- office.routers.misc        /skills、/usage、/context、/stats、/health、/approvals、旧路径指引
详见包内 REFACTOR_NOTES.md（原行号 → 新文件对照表）。
"""
