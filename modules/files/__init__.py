# -*- coding: utf-8 -*-
"""文件服务器模块 (File Server Module) — 依赖用户模块（modules.user）。

拥有文件上传/下载/删除、分类整理、孤儿清理等能力。孤儿清理端点
（POST /api/admin/cleanup）从原 admin 模块迁移至此，保持用户模块对文件模块
无反向依赖。
"""

from modules.common import create_app
from modules.files.categories import router as categories_router
from modules.files.cleanup import router as cleanup_router
from modules.files.files import router as files_router

SERVICE_NAME = "MinePython"
SERVICE_VERSION = "4.6.0"
SERVICE_DESCRIPTION = (
    "MinePython 文件服务器模块 —— 提供文件上传/下载/管理、分类整理、孤儿清理等接口。"
    "依赖用户模块提供的认证与 RBAC。"
)


def create_files_app():
    """Build the standalone file-server module app (own port, depends on user)."""
    return create_app(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=SERVICE_DESCRIPTION,
        routers=[files_router, categories_router, cleanup_router],
        extra_pages=[("/files.html", "files.html")],
        include_api_docs=True,
    )
