# -*- coding: utf-8 -*-
"""MinePython — modular layout.

总体项目 MinePython 拆分为四个相互独立、可单独启动的模块：

  modules/user    用户模块   —— 基座：认证 / 鉴权(RBAC) / 用户管理 / 数据库层
  modules/files   文件服务器 —— 依赖 user：文件上传下载、分类整理、孤儿清理
  modules/audit   审计模块   —— 依赖 user：审计日志查询
  modules/apidocs API 文档模块 —— 独立：聚合各模块 OpenAPI 的文档门户

依赖方向：files -> user ， audit -> user 。 user 不依赖任何业务模块，
因此可以被 files / audit 安全复用，而不会产生循环依赖。
"""
