# -*- coding: utf-8 -*-
"""用户模块 (User Module) — 基座。

持有共享基础设施：配置、数据库引擎与全部 ORM 模型、RBAC、认证与鉴权、
工具函数、日志。文件服务器与审计模块都依赖本模块。
"""

from modules.user.admin import router as admin_router
from modules.user.auth import router as auth_router
from modules.user.config import APP_NAME as SERVICE_NAME

from modules.version import VERSION as SERVICE_VERSION
SERVICE_DESCRIPTION = (
    f"{SERVICE_NAME} 用户与鉴权模块 —— 提供登录、令牌管理、用户与角色(RBAC)管理、"
    "管理员控制台等接口。文件服务器与审计模块均依赖本基座。"
)


def create_user_app():
    """Build the standalone user module app (own port, base for other modules).

    ``create_app`` is imported lazily to avoid a circular import: ``common``
    imports from ``modules.user`` (config/database/auth) at module load, while
    this package builds its app via ``common.create_app``.
    """
    from modules.common import create_app

    return create_app(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=SERVICE_DESCRIPTION,
        routers=[auth_router, admin_router],
        extra_pages=[
            ("/login.html", "login.html"),
            ("/register.html", "register.html"),
            ("/users.html", "users.html"),
        ],
        include_api_docs=True,
    )
