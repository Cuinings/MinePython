# -*- coding: utf-8 -*-
"""File business logic (ARCH-6).

Pure-ish helpers for upload validation, physical persistence and DB-record
creation. The route handlers in :mod:`modules.files.files` still own request
parsing, permission checks and response shaping, but delegate the actual
file/record work here. Keeping ``_insert_file_record`` commit-free lets callers
batch a multi-upload into one transaction (ARCH-7 atomicity).
"""

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

import modules.user.config as _cfg
from modules.user.database import File as FileModel


def validate_upload(filename: str, size: int) -> None:
    """Validate upload against configured limits. Raises HTTPException on violation."""
    ext = Path(filename).suffix.lower()
    if _cfg.ALLOWED_EXTENSIONS and ext not in _cfg.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is not allowed")
    if _cfg.BLOCKED_EXTENSIONS and ext in _cfg.BLOCKED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is blocked")
    if size > _cfg.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            400, f"File exceeds max size of {_cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB"
        )


def save_file(file: UploadFile, category: str) -> tuple[Path, str, int]:
    """Persist an uploaded file to its category directory; return (dest, stored_name, size)."""
    cat_dir = _cfg.UPLOAD_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{uid}_{file.filename}"
    dest = cat_dir / safe_name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest, safe_name, dest.stat().st_size


def insert_file_record(
    db: Session, stored_name: str, category: str, size: int, username: str, ip: str
) -> None:
    """Stage a File row. The caller commits (so batch uploads commit once and a
    mid-batch failure rolls back cleanly) — this guarantees "DB record present
    ⟺ physical file present" (ARCH-7)."""
    db.add(
        FileModel(
            filename=stored_name,
            category=category,
            filepath=f"{category}/{stored_name}",
            size=size,
            uploaded_by=username,
            uploaded_ip=ip,
        )
    )
