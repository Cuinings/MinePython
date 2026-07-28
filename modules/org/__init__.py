# -*- coding: utf-8 -*-
"""组织架构模块 (Organization Module) — 依赖用户模块（modules.user）。

提供部门树与成员的增删改查接口（/api/org）。权限与审计复用用户模块。
"""

from modules.org.org import router as org_router

__all__ = ["org_router"]
