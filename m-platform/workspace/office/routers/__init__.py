"""
office.routers —— 路由子包。各模块持 APIRouter，由 office.app.create_app 统一 include；
router 之间只允许横向引用叶子模块（如 misc → tasks 的 TASKS/_lock），禁止反向 import office.app。
"""
