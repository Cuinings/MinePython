# -*- coding: utf-8 -*-
"""建议栏模块 (Suggestion Module) — 依赖用户模块（modules.user）。

提供功能需求 / 建议的提交与查看接口（/api/suggest）。权限与审计复用用户模块。
"""

from modules.suggest.suggest import router as suggest_router

__all__ = ["suggest_router"]
