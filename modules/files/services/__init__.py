# -*- coding: utf-8 -*-
"""文件模块服务层 —— 上传/分类业务逻辑（依赖用户模块基座）。"""

from modules.files.services import category_service, file_service

__all__ = ["file_service", "category_service"]
