# -*- coding: utf-8 -*-
"""File endpoints: list, upload, download, delete."""

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.auth import get_current_user
from app.config import MAX_UPLOAD_SIZE_BYTES, ALLOWED_EXTENSIONS, BLOCKED_EXTENSIONS
from app.database import get_db
from app.utils import _categorize, _format_size

log = logging.getLogger("uvicorn")
router = APIRouter(prefix="/api", tags=["Files"])


def _validate_upload(filename: str, size: int):
    """Validate upload against configured limits. Raises HTTPException on violation."""
    ext = Path(filename).suffix.lower()
    if ALLOWED_EXTENSIONS and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is not allowed")
    if BLOCKED_EXTENSIONS and ext in BLOCKED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is blocked")
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(400, f"File exceeds max size of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")


@router.get("/files")
async def list_files(category: str | None = None):
    """List all files, optionally filtered by category."""
    db = get_db()
    if category:
        rows = db.execute(
            "SELECT * FROM files WHERE category = ? ORDER BY uploaded_at DESC", (category,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM files ORDER BY uploaded_at DESC").fetchall()
    db.close()

    result = []
    for r in rows:
        d = dict(r)
        d["path"] = d["filepath"]
        d["size_human"] = _format_size(d["size"])
        result.append(d)
    return {"files": result}


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(default="auto"),
    authorization: str = Header(default=""),
):
    """Upload a single file. category='auto' for auto-detection."""
    user = get_current_user(authorization)
    if category == "auto" or not category:
        category = _categorize(file.filename)

    # Validate upload
    _validate_upload(file.filename, file.size if hasattr(file, 'size') and file.size else 0)

    from app.config import UPLOAD_DIR
    cat_dir = UPLOAD_DIR / category
    cat_dir.mkdir(exist_ok=True)

    # Unique filename to avoid collision
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{uid}_{file.filename}"
    dest = cat_dir / safe_name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    file_size = dest.stat().st_size

    db = get_db()
    db.execute(
        "INSERT INTO files (filename, category, filepath, size, uploaded_by, uploaded_ip) VALUES (?,?,?,?,?,?)",
        (safe_name, category, f"{category}/{safe_name}", file_size,
         user["username"] if user else "anonymous",
         request.client.host if request.client else ""),
    )
    db.commit()
    db.close()

    return {"ok": True, "filename": file.filename, "category": category,
            "size": file_size, "size_fmt": _format_size(file_size)}


@router.post("/upload/multiple")
async def upload_multiple(
    request: Request,
    files: list[UploadFile] = File(...),
    category: str = Form(default="auto"),
    authorization: str = Header(default=""),
):
    """Batch upload multiple files."""
    user = get_current_user(authorization)
    results = []

    for file in files:
        cat = category if category != "auto" and category else _categorize(file.filename)
        from app.config import UPLOAD_DIR
        cat_dir = UPLOAD_DIR / cat
        cat_dir.mkdir(exist_ok=True)

        uid = uuid.uuid4().hex[:8]
        safe_name = f"{uid}_{file.filename}"
        dest = cat_dir / safe_name

        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        file_size = dest.stat().st_size

        db = get_db()
        db.execute(
            "INSERT INTO files (filename, category, filepath, size, uploaded_by, uploaded_ip) VALUES (?,?,?,?,?,?)",
            (safe_name, cat, f"{cat}/{safe_name}", file_size,
             user["username"] if user else "anonymous",
             request.client.host if request.client else ""),
        )
        db.commit()
        db.close()

        results.append({"filename": file.filename, "category": cat, "size": file_size,
                        "size_fmt": _format_size(file_size)})

    return {"ok": True, "count": len(results), "files": results}


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """Download a file by its stored path."""
    from app.config import UPLOAD_DIR
    full = UPLOAD_DIR / file_path
    if not full.exists() or not full.is_file():
        from fastapi import HTTPException
        raise HTTPException(404, "File not found")

    # Get original filename from DB
    db = get_db()
    row = db.execute("SELECT filename FROM files WHERE filepath = ?", (file_path,)).fetchone()
    db.close()
    original = row["filename"] if row else full.name
    # Strip uuid prefix for download name
    display_name = original.split("_", 1)[1] if "_" in original else original

    return FileResponse(full, filename=display_name)


@router.delete("/files/{file_path:path}")
async def delete_file(file_path: str):
    """Delete a file record and its physical file."""
    from app.config import UPLOAD_DIR
    import logging
    log = logging.getLogger("uvicorn")

    full = UPLOAD_DIR / file_path
    log.info(f"Delete: file_path={file_path}, full={full}, exists={full.exists()}")

    db = get_db()
    row = db.execute("SELECT id FROM files WHERE filepath = ?", (file_path,)).fetchone()
    if not row:
        db.close()
        from fastapi import HTTPException
        raise HTTPException(404, "File not found")

    db.execute("DELETE FROM files WHERE id = ?", (row["id"],))
    db.commit()
    db.close()

    try:
        if full.exists():
            full.unlink()
            log.info(f"File deleted from disk: {full}")
    except Exception as e:
        log.error(f"Failed to unlink {full}: {e}")

    return {"ok": True, "message": "File deleted"}
