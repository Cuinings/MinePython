# -*- coding: utf-8 -*-
"""合并入口：把四个模块挂到同一个 FastAPI 应用（端口 8000）。

保留现有前端 UI（index.html / login.html / register.html / files.html /
users.html / audit.html / api.html）完全不动；各模块的路由器与页面统一注册到这里。
这是 ``python -m modules`` 与
``server.py`` 实际运行的应用。测试也从这里导入 ``app`` 对象。
"""

from modules.audit.audit import router as audit_router
from modules.common import create_app
from modules.suggest.suggest import router as suggest_router
from modules.org.org import router as org_router
from modules.files.adb import router as adb_router
from modules.files.categories import router as categories_router
from modules.files.cleanup import router as cleanup_router
from modules.files.files import router as files_router
from modules.user.admin import router as admin_router
from modules.user.auth import router as auth_router
from modules.user.config import APP_NAME as SERVICE_NAME

from modules.version import VERSION as SERVICE_VERSION
SERVICE_DESCRIPTION = (
    f"{SERVICE_NAME} REST API —— 提供用户鉴权、文件上传/下载/管理、分类整理、审计日志与功能建议等接口。"
)


def create_combined_app():
    """Assemble the single combined application that hosts all four modules."""
    return create_app(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=SERVICE_DESCRIPTION,
        routers=[auth_router, admin_router, files_router, categories_router, cleanup_router, audit_router, adb_router, suggest_router, org_router],
        extra_pages=[
            ("/login.html", "login.html"),
            ("/register.html", "register.html"),
            ("/files.html", "files.html"),
            ("/users.html", "users.html"),
            ("/audit.html", "audit.html"),
            ("/settings.html", "settings.html"),
        ],
        include_api_docs=True,
    )


# Module-level app object so tests can `from modules.combined import app`.
app = create_combined_app()
