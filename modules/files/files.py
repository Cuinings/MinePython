# -*- coding: utf-8 -*-
"""File endpoints: list, upload, download, delete (RBAC-gated)."""

import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modules.user.auth import (
    authenticate_token,
    get_current_user,
    require_permission,
    require_permission_allow_anonymous,
)
from modules.user.config import (
    ALLOWED_EXTENSIONS,
    BLOCKED_EXTENSIONS,
    MAX_BATCH_DOWNLOAD_BYTES,
    MAX_BATCH_DOWNLOAD_FILES,
    MAX_UPLOAD_SIZE_BYTES,
    UPLOAD_DIR,
)
from modules.user.database import File as FileModel
from modules.user.database import User, get_db, get_permissions_for_role, orm_to_dict
from modules.user.models import FileListResponse, PathsRequest
from modules.files.services import file_service
from modules.user.utils import _audit_log, _categorize, _delete_file, _format_size

log = logging.getLogger("uvicorn")
router = APIRouter(prefix="/api", tags=["Files"])


@router.get("/files", response_model=FileListResponse)
async def list_files(
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission_allow_anonymous("file:list")),
):
    """List files with optional category filter, pagination, and search."""
    stmt = select(FileModel)
    if category:
        stmt = stmt.where(FileModel.category == category)
    if search:
        stmt = stmt.where(FileModel.filename.like(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    offset = max(0, (page - 1) * page_size)
    rows = db.execute(
        stmt.order_by(FileModel.uploaded_at.desc()).limit(page_size).offset(offset)
    ).scalars().all()

    result = []
    uploaders = {f.uploaded_by for f in rows if f.uploaded_by and f.uploaded_by != "anonymous"}
    nick_map: dict[str, str] = {}
    if uploaders:
        nick_rows = db.execute(
            select(User.username, User.nickname).where(User.username.in_(uploaders))
        ).all()
        nick_map = {u: (n or u) for u, n in nick_rows}

    for f in rows:
        d = orm_to_dict(f)
        d["path"] = d["filepath"]
        d["size_human"] = _format_size(d["size"])
        uname = d.get("uploaded_by") or "anonymous"
        d["uploader_nickname"] = nick_map.get(uname) or uname
        result.append(d)

    return {"files": result, "total": total, "page": page, "page_size": page_size}


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(default="auto"),
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("file:upload")),
):
    """Upload a single file (requires file:upload). category='auto' for auto-detection."""
    if category == "auto" or not category:
        category = _categorize(file.filename)

    size = file.size if hasattr(file, "size") and file.size else 0
    file_service.validate_upload(file.filename, size)

    dest, safe_name, file_size = file_service.save_file(file, category)
    ip = request.client.host if request.client else ""

    try:
        file_service.insert_file_record(db, safe_name, category, file_size, user["username"], ip)
        db.commit()
    except Exception:
        _delete_file(dest)
        raise

    _audit_log("upload", file.filename, user["username"], ip)

    return {
        "ok": True,
        "filename": file.filename,
        "category": category,
        "size": file_size,
        "size_fmt": _format_size(file_size),
    }


@router.post("/upload/multiple")
async def upload_multiple(
    request: Request,
    files: list[UploadFile] = File(...),
    category: str = Form(default="auto"),
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("file:upload")),
):
    """Batch upload multiple files (requires file:upload)."""
    ip = request.client.host if request.client else ""
    results = []
    saved_physical: list[Path] = []

    try:
        for file in files:
            cat = category if category not in ("auto", "") else _categorize(file.filename)
            size = file.size if hasattr(file, "size") and file.size else 0
            file_service.validate_upload(file.filename, size)

            dest, safe_name, file_size = file_service.save_file(file, cat)
            saved_physical.append(dest)
            file_service.insert_file_record(db, safe_name, cat, file_size, user["username"], ip)
            results.append({
                "filename": file.filename,
                "category": cat,
                "size": file_size,
                "size_fmt": _format_size(file_size),
            })
        db.commit()
    except Exception:
        for p in saved_physical:
            _delete_file(p)
        raise

    _audit_log("upload_multiple", f"{len(results)} files", user["username"], ip)

    return {"ok": True, "count": len(results), "files": results}


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    token: str | None = None,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Download a file by its stored path."""
    user = get_current_user(authorization) or authenticate_token(token)
    if not user:
        if "file:download" in get_permissions_for_role("anonymous"):
            user = {"role": "anonymous", "username": "anonymous", "anonymous": True}
    if not user:
        raise HTTPException(401, "Authentication required")
    if "file:download" not in get_permissions_for_role(user["role"]):
        raise HTTPException(403, "Permission 'file:download' required")

    full = UPLOAD_DIR / file_path
    if not full.exists() or not full.is_file():
        raise HTTPException(404, "File not found")

    row = db.execute(select(FileModel).where(FileModel.filepath == file_path)).scalar_one_or_none()
    original = row.filename if row else full.name
    display_name = original.split("_", 1)[1] if "_" in original else original
    return FileResponse(full, filename=display_name)


@router.get("/preview/{file_path:path}")
async def preview_file(
    file_path: str,
    token: str | None = None,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Inline preview of a file (P1-3)."""
    user = get_current_user(authorization) or authenticate_token(token)
    if not user:
        if "file:download" in get_permissions_for_role("anonymous"):
            user = {"role": "anonymous", "username": "anonymous", "anonymous": True}
    if not user:
        raise HTTPException(401, "Authentication required")
    if "file:download" not in get_permissions_for_role(user["role"]):
        raise HTTPException(403, "Permission 'file:download' required")

    full = UPLOAD_DIR / file_path
    if not full.exists() or not full.is_file():
        raise HTTPException(404, "File not found")

    row = db.execute(select(FileModel).where(FileModel.filepath == file_path)).scalar_one_or_none()
    original = row.filename if row else full.name
    display_name = original.split("_", 1)[1] if "_" in original else original
    media_type = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
    return FileResponse(
        full,
        media_type=media_type,
        filename=display_name,
        content_disposition_type="inline",
    )


@router.delete("/files/{file_path:path}")
async def delete_file(
    file_path: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a file record and its physical file."""
    if not user:
        raise HTTPException(401, "Authentication required")

    row = db.execute(select(FileModel).where(FileModel.filepath == file_path)).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "File not found")

    perms = get_permissions_for_role(user["role"])
    is_owner = row.uploaded_by == user["username"]
    if not ((is_owner and "file:delete_self" in perms) or "file:delete_any" in perms):
        raise HTTPException(403, "Permission denied: cannot delete this file")

    db.delete(row)
    db.commit()
    _audit_log("delete", file_path, user["username"])

    full = UPLOAD_DIR / file_path
    if not _delete_file(full):
        log.error(f"Physical file {full} could not be deleted after its DB record was removed")

    return {"ok": True, "message": "File deleted"}


@router.post("/files/batch-delete")
async def batch_delete_files(
    body: PathsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete multiple files in one request."""
    if not user:
        raise HTTPException(401, "Authentication required")

    perms = get_permissions_for_role(user["role"])
    can_any = "file:delete_any" in perms
    can_self = "file:delete_self" in perms
    if not (can_any or can_self):
        raise HTTPException(403, "Permission denied: cannot delete files")

    if not body.paths:
        raise HTTPException(400, "No files selected")

    deleted, failed = [], []
    candidates = []
    for path in body.paths:
        row = db.execute(select(FileModel).where(FileModel.filepath == path)).scalar_one_or_none()
        if not row:
            failed.append({"path": path, "error": "not found"})
            continue
        is_owner = row.uploaded_by == user["username"]
        if not ((is_owner and can_self) or can_any):
            failed.append({"path": path, "error": "forbidden"})
            continue
        candidates.append((row, UPLOAD_DIR / path))

    if candidates:
        for row, _ in candidates:
            db.delete(row)
        db.commit()
        _audit_log("batch_delete", f"{len(candidates)} files", user["username"])

    for row, full in candidates:
        if _delete_file(full):
            deleted.append(row.filepath)
        else:
            failed.append({"path": row.filepath, "error": "physical delete failed"})

    return {"ok": True, "deleted": deleted, "failed": failed, "count": len(deleted)}


@router.post("/files/batch-download")
async def batch_download_files(
    body: PathsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("file:download")),
):
    """Download multiple files as a single ZIP archive."""
    if not body.paths:
        raise HTTPException(400, "No files selected")

    if len(body.paths) > MAX_BATCH_DOWNLOAD_FILES:
        raise HTTPException(
            400,
            f"Too many files selected ({len(body.paths)}); "
            f"limit is {MAX_BATCH_DOWNLOAD_FILES}.",
        )

    total_bytes = db.scalar(
        select(func.coalesce(func.sum(FileModel.size), 0)).where(
            FileModel.filepath.in_(body.paths)
        )
    ) or 0
    if total_bytes > MAX_BATCH_DOWNLOAD_BYTES:
        raise HTTPException(
            400,
            f"Total size {total_bytes // (1024 * 1024)}MB exceeds the "
            f"{MAX_BATCH_DOWNLOAD_BYTES // (1024 * 1024)}MB download limit.",
        )

    used_names: set[str] = set()
    packed = 0
    tmp = tempfile.NamedTemporaryFile(prefix="batch_dl_", suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in body.paths:
                row = db.execute(
                    select(FileModel).where(FileModel.filepath == path)
                ).scalar_one_or_none()
                full = UPLOAD_DIR / path
                if not row or not full.exists() or not full.is_file():
                    continue
                original = row.filename
                display = original.split("_", 1)[1] if "_" in original else original
                final = display
                n = 2
                while final in used_names:
                    stem, dot, ext = display.rpartition(".")
                    final = (stem + f" ({n})" + dot + ext) if dot else f"{display} ({n})"
                    n += 1
                used_names.add(final)
                zf.write(str(full), arcname=final)
                packed += 1

        if packed == 0:
            os.remove(tmp_path)
            raise HTTPException(404, "No files found to download")

        size = os.path.getsize(tmp_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        headers = {
            "Content-Disposition": f"attachment; filename=files_{stamp}.zip",
            "Content-Length": str(size),
        }

        def iter_chunks():
            try:
                with open(tmp_path, "rb") as fh:
                    while True:
                        chunk = fh.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return StreamingResponse(iter_chunks(), media_type="application/zip", headers=headers)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
