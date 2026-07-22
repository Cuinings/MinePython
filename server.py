# -*- coding: utf-8 -*-
"""
MinePython v4.6 — thin entry point.
http://localhost:8000 for Web UI, /docs for Swagger.

All application logic now lives in the modules/ package:
  modules/user/       — 基座：配置、数据库、RBAC、认证、用户/管理员控制台
  modules/files/      — 文件服务器：上传/下载/管理、分类整理、孤儿清理
  modules/audit/      — 审计模块：审计日志查询
  modules/apidocs/    — API 文档门户
  modules/combined.py — 把四个模块挂到同一个应用（端口 8000）
"""

from modules.combined import app

if __name__ == "__main__":
    import uvicorn
    from sqlalchemy import func, select

    from modules.user.config import DB_PATH, UPLOAD_DIR, HOST, PORT
    from modules.user.database import File, SessionLocal, User, init_db
    from modules.user.logging_config import setup_logging

    # Configure logging (rotating JSON file + console) before uvicorn starts.
    # uvicorn is told NOT to install its own logging config / access logger so
    # that all output flows through our handlers (structured + redacted).
    setup_logging()

    init_db()

    # Print startup info
    with SessionLocal() as db:
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
        file_count = db.scalar(select(func.count()).select_from(File)) or 0

    print(f"\n  MinePython v4.6")
    print(f"  {'-' * 30}")
    print(f"  Web UI:     http://localhost:8000")
    print(f"  API Home:   http://localhost:8000/api")
    print(f"  Swagger:    http://localhost:8000/docs")
    print(f"  Database:   {DB_PATH}")
    print(f"  Users:      {user_count} registered")
    print(f"  Files:      {file_count} records")
    print(f"  Storage:    {UPLOAD_DIR}")
    print(f"  {'-' * 30}\n")

    uvicorn.run(
        "modules.combined:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_config=None,   # we own logging (see modules.user.logging_config)
        access_log=False,  # our request middleware logs access structurally
    )
