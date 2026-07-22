# -*- coding: utf-8 -*-
"""审计模块 (Audit Module) — 依赖用户模块（modules.user）。

提供审计日志查询端点（/api/audit/logs），所有登录用户可查看本人记录，
管理员/审计员可查看全部记录。审计日志的物理存储与 RBAC 校验复用用户模块。
"""

from modules.audit.audit import router as audit_router
from modules.common import create_app

SERVICE_NAME = "MinePython"
SERVICE_VERSION = "4.6.0"
SERVICE_DESCRIPTION = (
    "MinePython 审计模块 —— 提供操作记录与安全审计日志查询接口。"
)


def create_audit_app():
    """Build the standalone audit module app (own port, depends on user module)."""
    return create_app(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=SERVICE_DESCRIPTION,
        routers=[audit_router],
        extra_pages=[("/audit.html", "audit.html")],
        include_api_docs=True,
    )
