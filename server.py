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
    from app.database import init_db
    from app.config import DB_PATH, UPLOAD_DIR
    from pathlib import Path

    init_db()

    # Print startup info
    db = __import__('app.database', fromlist=['get_db']).get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    file_count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    db.close()

    print(f"\n  File Server v4.2")
    print(f"  {'-' * 30}")
    print(f"  Web UI:     http://localhost:8000")
    print(f"  Swagger:    http://localhost:8000/docs")
    print(f"  Database:   {DB_PATH}")
    print(f"  Users:      {user_count} registered")
    print(f"  Files:      {file_count} records")
    print(f"  Storage:    {UPLOAD_DIR}")
    print(f"  {'-' * 30}\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
