"""助手「工作平台·后台任务队列」— 装配壳（R10.8 拆分后入口）
=====================================================================
原 1901 行已按职责拆分为 office/ 包：
  core.py       — 公共纯函数层（_secrets_dir/_ck/_rate_ok/_rotate_log/_token_audit/_presented_token）
  app.py        — FastAPI app 装配（中间件叠放+路由注册+守卫名单）
  routers/      — 7 个路由模块（providers/rag/gates/tasks/token_admin/misc）
详情

langgraph.json 引用 `./office.py:app` — 本壳只做一行 re-export。
"""
from office.app import app  # noqa: F401

if __name__ == "__main__":  # R10.9（hy4 审查 P1-1）：保留 `python office.py` 直接启动习惯（原 :1900-1901）
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=2024, log_level="info")
