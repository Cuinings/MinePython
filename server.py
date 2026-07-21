# -*- coding: utf-8 -*-
"""
File Server v4.2 — thin entry point.
http://localhost:8000 for Web UI, /docs for Swagger.

All application logic lives in the app/ package:
  app/config.py      — constants, paths, extension mapping
  app/database.py    — SQLite connection, schema init & migration
  app/models.py      — Pydantic request/response models
  app/utils.py       — password hashing, file categorization, formatting
  app/auth.py        — login/register endpoints, auth helpers
  app/admin.py       — admin user CRUD, approval, pending count
  app/files.py       — file list, upload, download, delete
  app/categories.py  — category list, delete, organize
  app/main.py        — FastAPI app assembly, CORS, Web UI
"""

if __name__ == "__main__":
    import uvicorn
    from sqlalchemy import func, select

    from app.config import DB_PATH, UPLOAD_DIR, HOST, PORT
    from app.database import File, SessionLocal, User, init_db
    from app.logging_config import setup_logging

    # Configure logging (rotating JSON file + console) before uvicorn starts.
    # uvicorn is told NOT to install its own logging config / access logger so
    # that all output flows through our handlers (structured + redacted).
    setup_logging()

    init_db()

    # Print startup info
    with SessionLocal() as db:
        user_count = db.scalar(select(func.count()).select_from(User)) or 0
        file_count = db.scalar(select(func.count()).select_from(File)) or 0

    print(f"\n  File Server v4.6")
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
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_config=None,   # we own logging (see app.logging_config)
        access_log=False,  # our request middleware logs access structurally
    )
