# -*- coding: utf-8 -*-
"""File endpoints: list, upload, download, delete (RBAC-gated)."""

import logging
import mimetypes
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime

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
    MAX_USER_UPLOAD_BYTES,
    UPLOAD_DIR,
)
from modules.user.database import File as FileModel
from modules.user.database import User, get_db, get_permissions_for_role, orm_to_dict
from modules.user.models import FileListResponse, PathsRequest
from modules.files.services import file_service
from modules.user.utils import _audit_log, _categorize, _client_ip, _delete_file, _format_size

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


@router.get("/stats/home")
async def home_stats(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Dashboard stats for the home view (any authenticated user).

    Returns real numbers the home page renders: total files / total size,
    the caller's own file count / size, the configured per-user quota (MB,
    0 = disabled), the count of pending (awaiting-approval) registrations,
    and the 6 most recently uploaded files. Kept as a single cheap aggregate
    query so the home page can show a real dashboard without N round-trips.
    """
    if not user:
        raise HTTPException(401, "Authentication required")

    username = user["username"]
    role = user["role"]

    total_files = db.scalar(select(func.count()).select_from(FileModel)) or 0
    total_size = db.scalar(select(func.coalesce(func.sum(FileModel.size), 0))) or 0
    my_files = (
        db.scalar(
            select(func.count())
            .select_from(FileModel)
            .where(FileModel.uploaded_by == username)
        )
        or 0
    )
    my_size = (
        db.scalar(
            select(func.coalesce(func.sum(FileModel.size), 0))
            .select_from(FileModel)
            .where(FileModel.uploaded_by == username)
        )
        or 0
    )

    # Per-user quota (admin-configured, 0 = disabled). Reported to everyone so
    # the storage bar can render even for non-admins subject to it.
    quota_mb = MAX_USER_UPLOAD_BYTES // (1024 * 1024)

    # Pending registrations — shown to approvers (admin / reviewer). It's only
    # a count (no identities), so it's safe to compute for any caller.
    pending_users = 0
    if role in ("admin", "reviewer"):
        pending_users = (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.status == "pending")
            )
            or 0
        )

    # 6 most recent files (same shape as /api/files rows).
    rows = (
        db.execute(
            select(FileModel)
            .order_by(FileModel.uploaded_at.desc())
            .limit(6)
        )
        .scalars()
        .all()
    )
    recent = []
    if rows:
        uploaders = {f.uploaded_by for f in rows if f.uploaded_by and f.uploaded_by != "anonymous"}
        nick_map = {}
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
            recent.append(d)

    return {
        "ok": True,
        "total_files": total_files,
        "total_size": total_size,
        "my_files": my_files,
        "my_size": my_size,
        "quota_mb": quota_mb,
        "pending_users": pending_users,
        "recent": recent,
    }


# Serialize the "quota check + insert + commit" DB section of /api/upload so
# concurrent per-file uploads can't overshoot the per-user quota by racing the
# committed-total read (P5 race). The disk write itself stays concurrent.
QUOTA_LOCK = threading.Lock()


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

    # Disk write is concurrent (cheap I/O); the DB commit + quota/rate
    # checks are serialized via QUOTA_LOCK so concurrent uploads can't
    # overshoot the per-user quota by racing the committed-total read (P5).
    dest, safe_name, file_size, category = file_service.save_file(file, category)
    ip = request.client.host if request.client else ""
    try:
        with QUOTA_LOCK:
            file_service._check_rate_limit(user["username"])
            file_service.check_user_quota(db, user["username"], file_size)
            file_service.insert_file_record(db, safe_name, category, file_size, user["username"], ip)
            db.commit()
    except Exception:
        _delete_file(dest)
        raise

    _audit_log("upload", file.filename, user["username"], ip)

    return {
        "ok": True,
        "filename": file.filename,
        "path": f"{category}/{safe_name}",
        "category": category,
        "size": file_size,
        "size_fmt": _format_size(file_size),
    }


# NOTE: batch upload is handled client-side via per-file concurrent uploads
# (see files.html `uploadFiles`). Keeping it here would duplicate the
# per-user quota / rate-limit / streaming-size guards and is no longer called.


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    token: str | None = None,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
    request: Request = None,
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
    # Audit: every successful download is recorded (incl. anonymous guests, who
    # are attributed to the synthetic "anonymous" user). Closes the
    # download-untracked gap in the audit trail.
    _audit_log("download", file_path, user.get("username", "anonymous"), _client_ip(request))
    return FileResponse(
        full,
        filename=display_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/preview/{file_path:path}")
async def preview_file(
    file_path: str,
    token: str | None = None,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Inline preview of a file (P1-3).

    User-supplied HTML / SVG / XML / script content is served with
    ``Content-Disposition: attachment`` and ``X-Content-Type-Options:
    nosniff`` so it can never execute inline in the victim's session
    (stored XSS via preview). Only genuinely safe media types render inline.
    """
    # Media types that must NOT be rendered inline (would execute in the
    # viewer's authenticated session). Served as attachment instead.
    INLINE_UNSAFE = {
        "text/html", "application/xhtml+xml", "image/svg+xml",
        "application/javascript", "text/javascript", "text/xml", "application/xml",
    }
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
    disp = "inline" if media_type not in INLINE_UNSAFE else "attachment"
    return FileResponse(
        full,
        media_type=media_type,
        filename=display_name,
        content_disposition_type=disp,
        headers={"X-Content-Type-Options": "nosniff"},
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
