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

    from modules.user.config import APP_NAME, DB_PATH, UPLOAD_DIR, HOST, PORT
    from modules.user.database import File, SessionLocal, User, init_db
    from modules.user.logging_config import setup_logging

    # Configure logging (rotating JSON file + console) before uvicorn starts.
    # uvicorn is told NOT to install its own logging config / access logger so
    # that all output flows through our handlers (structured + redacted).
    setup_logging()

    init_db()

    # --- Optional HTTPS -------------------------------------------------------
    # WebUSB (browser ADB install) requires a secure context, so the page
    # MUST be served over HTTPS. Enable it by pointing these env vars at a
    # cert/key pair (self-signed is fine for internal/LAN use — the user
    # just has to accept the browser warning once). When unset, uvicorn
    # falls back to plain HTTP so nothing breaks for existing deployments.
    import os
    ssl_certfile = os.environ.get("SSL_CERTFILE") or os.environ.get("SSL_CERT_FILE")
    ssl_keyfile = os.environ.get("SSL_KEYFILE") or os.environ.get("SSL_KEY_FILE")
    # Enable TLS only when BOTH a cert and a key are set AND exist on disk.
    # A missing/bad cert must NOT crash the server — it degrades to plain HTTP.
    if ssl_certfile and ssl_keyfile and os.path.exists(ssl_certfile) and os.path.exists(ssl_keyfile):
        scheme = "https"
        _tls_note = "ENABLED (" + ssl_certfile + ")"
    else:
        ssl_certfile = ssl_keyfile = None
        scheme = "http"
        if os.environ.get("SSL_CERTFILE") or os.environ.get("SSL_KEYFILE"):
            _tls_note = "DISABLED — SSL_* set but file(s) missing, fell back to HTTP"
        else:
            _tls_note = "disabled (HTTP) — WebUSB needs HTTPS; set SSL_CERTFILE/SSL_KEYFILE"

    # Print startup info
    with SessionLocal() as db:
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
        file_count = db.scalar(select(func.count()).select_from(File)) or 0

    print(f"\n  {APP_NAME} v4.6")
    print(f"  {'-' * 30}")
    print(f"  Web UI:     {scheme}://localhost:{PORT}")
    print(f"  API Home:   {scheme}://localhost:{PORT}/api")
    print(f"  Swagger:    {scheme}://localhost:{PORT}/docs")
    print(f"  Database:   {DB_PATH}")
    print(f"  Users:      {user_count} registered")
    print(f"  Files:      {file_count} records")
    print(f"  Storage:    {UPLOAD_DIR}")
    print(f"  TLS:        {_tls_note}")
    print(f"  {'-' * 30}\n")

    uvicorn.run(
        "modules.combined:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_config=None,   # we own logging (see modules.user.logging_config)
        access_log=False,  # our request middleware logs access structurally
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
