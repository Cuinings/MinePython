# -*- coding: utf-8 -*-
"""API 文档模块 (API Docs Module)。

独立的 API 文档门户：在自身端口提供 Swagger/ReDoc 与 /api 文档主页。它不挂载
任何业务路由，仅复用公共层的文档开关与 /api 页面渲染，因此可与其它模块解耦部署，
也可由 nginx 反向代理聚合到统一域名下。
"""

from fastapi.responses import RedirectResponse

from modules.common import create_app
from modules.user.config import APP_NAME as SERVICE_NAME

from modules.version import VERSION as SERVICE_VERSION
SERVICE_DESCRIPTION = (
    f"{SERVICE_NAME} API 文档门户 —— 聚合各模块的 OpenAPI 文档，提供交互式 Swagger / ReDoc。"
)


def create_apidocs_app():
    """Build the standalone API-docs portal app (own port)."""
    app = create_app(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=SERVICE_DESCRIPTION,
        routers=[],
        extra_pages=[],
        include_api_docs=True,
    )

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/api")

    return app
