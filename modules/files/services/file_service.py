# -*- coding: utf-8 -*-
"""File business logic (ARCH-6).

Pure-ish helpers for upload validation, physical persistence and DB-record
creation. The route handlers in :mod:`modules.files.files` still own request
parsing, permission checks and response shaping, but delegate the actual
file/record work here. Keeping ``_insert_file_record`` commit-free lets callers
batch a multi-upload into one transaction (ARCH-7 atomicity).
"""

import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import modules.user.config as _cfg
from modules.user.database import File as FileModel

log = logging.getLogger("fileserver")


# ---------------------------------------------------------------------------
# Path-traversal guard (P1 / security fix).
# Client-supplied ``category`` and ``filename`` must never be able to escape
# the intended upload directory. A malicious value like ``../etc`` or
# ``a/b/x.php`` is collapsed to its final single segment ("etc", "x.php");
# empty / "." / ".." collapses to "" so the caller can fall back to a safe
# default. This is the server-side authority -- the frontend cannot bypass it.
# ---------------------------------------------------------------------------
def _safe_segment(value: str) -> str:
    if not value:
        return ""
    seg = Path(value).name
    if seg in ("", ".", ".."):
        return ""
    # Defensive: drop any stray separators left behind by odd inputs.
    if any(ch in seg for ch in ("/", "\\")):
        seg = Path(seg).name
    return seg


# ---------------------------------------------------------------------------
# Per-user upload rate limiter (P5). Disabled when UPLOAD_RATE_LIMIT <= 0.
#
# Single-process default (in-memory sliding window). For multi-instance
# deployments (ARCH-10) point RATE_LIMIT_STORE at Redis — the limiter then
# counts shared across all instances. A Redis failure degrades gracefully to
# the in-memory path so an instance never hard-blocks uploads on a cache blip.
# ---------------------------------------------------------------------------
_RATE: dict[str, list[float]] = {}
_REDIS = None


def _get_redis():
    """Lazily build a Redis client from RATE_LIMIT_STORE (no hard dependency)."""
    global _REDIS
    if _REDIS is None and _cfg.RATE_LIMIT_STORE:
        try:
            import redis  # only needed for multi-instance deploys

            _REDIS = redis.from_url(_cfg.RATE_LIMIT_STORE, socket_connect_timeout=2)
        except Exception:
            log.exception("Failed to connect to RATE_LIMIT_STORE; using in-memory limiter")
            _REDIS = False  # don't retry every call
    return _REDIS or None


def _check_rate_limit(username: str) -> None:
    limit = _cfg.UPLOAD_RATE_LIMIT
    if limit <= 0:
        return
    window = _cfg.UPLOAD_RATE_WINDOW_SECONDS
    r = _get_redis()
    if r is not None:
        # Fixed-window counter: INCR + EXPIRE per window. Good enough for an
        # upload throttle and atomic under concurrency.
        key = f"ratelimit:upload:{username}"
        try:
            count = r.incr(key)
            if count == 1:
                r.expire(key, window)
            if count > limit:
                raise HTTPException(429, "Upload rate limit exceeded, please retry later")
            return
        except HTTPException:
            raise
        except Exception:
            log.warning("Redis rate-limit failed; falling back to in-memory")
            # fall through to in-memory below

    now = time.time()
    stamps = [t for t in _RATE.get(username, []) if now - t < window]
    if len(stamps) >= limit:
        raise HTTPException(429, "Upload rate limit exceeded, please retry later")
    stamps.append(now)
    _RATE[username] = stamps


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


def save_file(file: UploadFile, category: str) -> tuple[Path, str, int, str]:
    """Persist an uploaded file to its (sanitized) category directory.

    Returns ``(dest, stored_name, size, sanitized_category)``. The size limit is
    enforced while streaming (not just from the client-reported ``Content-Length``),
    so a request that omits / lies about its length cannot bypass it (P4). The
    category and filename are sanitized so a ``../`` or ``a/b/x`` value cannot
    escape the upload root (P1).
    """
    cat = _safe_segment(category) or _cfg.DEFAULT_CATEGORY
    cat_dir = _cfg.UPLOAD_DIR / cat
    cat_dir.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    base = _safe_segment(file.filename) or "file"
    safe_name = f"{uid}_{base}"
    dest = cat_dir / safe_name

    max_bytes = _cfg.MAX_UPLOAD_SIZE_BYTES
    chunk = 1024 * 1024
    written = 0
    try:
        with open(dest, "wb") as f:
            while True:
                data = file.file.read(chunk)
                if not data:
                    break
                written += len(data)
                if written > max_bytes:
                    raise HTTPException(
                        400,
                        f"File exceeds max size of {max_bytes // (1024 * 1024)}MB",
                    )
                f.write(data)
    except HTTPException:
        # Roll back the partial file on size rejection.
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return dest, safe_name, written, cat


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


def check_user_quota(db: Session, username: str, additional: int = 0) -> None:
    """Reject if the user's stored total would exceed ``MAX_USER_UPLOAD_BYTES``.

    No-op when the limit is 0/negative (default -- disabled). The ``additional``
    bytes are the size of the file about to be committed (P5).
    """
    limit = _cfg.MAX_USER_UPLOAD_BYTES
    if limit <= 0:
        return
    total = (
        db.scalar(
            select(func.coalesce(func.sum(FileModel.size), 0)).where(
                FileModel.uploaded_by == username
            )
        )
        or 0
    )
    if total + additional > limit:
        raise HTTPException(
            400,
            f"Quota exceeded: your uploads would exceed the "
            f"{limit // (1024 * 1024)}MB limit.",
        )
