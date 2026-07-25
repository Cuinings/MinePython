# -*- coding: utf-8 -*-
"""Admin endpoints: user CRUD, approval, pending count, audit log (RBAC-gated).

The user business logic has moved to :mod:`modules.user.services.user_service`;
the handlers here do permission guarding + request/response shaping and delegate
the actual work to the service.

The orphan-cleanup endpoint (``POST /api/admin/cleanup``) has been relocated to
the file-server module (:mod:`modules.files.cleanup`) so that this user module
stays free of any reverse dependency on the files module.
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from modules.user.auth import get_current_user, get_permissions_for_role, require_admin, require_permission
from modules.user.database import AuditLog, User, get_db, orm_to_dict, audit_logs_to_dicts
from modules.user.models import (
    AdminBatchRequest,
    AdminUserRequest,
    AuditClearRequest,
    AuditListResponse,
    PendingResponse,
    UserListResponse,
)
from modules.user import config
from modules.user.services import user_service
from modules.user.utils import _audit_log, _client_ip

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users", response_model=UserListResponse)
async def admin_list_users(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:read")),
):
    """List all users (requires user:read)."""
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return {"users": [user_service.user_to_dict(u) for u in users]}


@router.get("/pending", response_model=PendingResponse)
async def admin_pending_count(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:read")),
):
    """Get pending user count and list (requires user:read)."""
    rows = (
        db.execute(
            select(User.id, User.username, User.nickname)
            .where(User.status == "pending")
            .order_by(User.id)
        )
        .mappings()
        .all()
    )
    return {"count": len(rows), "users": [dict(r) for r in rows]}


@router.put("/users/{user_id}/approve")
async def admin_approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:approve")),
    request: Request = None,
):
    """Approve a pending user (requires user:approve)."""
    return user_service.approve_user(db, user_id, _client_ip(request))


@router.put("/users/{user_id}/reject")
async def admin_reject_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:approve")),
    request: Request = None,
):
    """Reject a pending user (requires user:approve). Sets status to 'rejected'."""
    return user_service.reject_user(db, user_id, _client_ip(request))


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permission("user:manage")),
    request: Request = None,
):
    """Delete a user (requires user:manage, cannot delete self or default admin)."""
    return user_service.delete_user(db, user_id, admin, _client_ip(request))


@router.post("/users")
async def admin_create_user(
    body: AdminUserRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:manage")),
    request: Request = None,
):
    """Create a new user (requires user:manage). Can set all fields."""
    return user_service.create_user(db, body, _client_ip(request))


@router.put("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    body: AdminUserRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("user:manage")),
    request: Request = None,
):
    """Modify user info (requires user:manage). All fields optional."""
    return user_service.update_user(db, user_id, body, _client_ip(request))


@router.post("/users/batch")
async def admin_batch_users(
    body: AdminBatchRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Batch user operations: approve / reject / delete.

    Permission gate is action-dependent:
      * approve / reject -> requires ``user:approve``
      * delete           -> requires ``user:manage`` (cannot delete self)
    Deleting a user also invalidates every one of their sessions.
    """
    if not user:
        raise HTTPException(401, "Authentication required")
    return user_service.batch_user_action(db, body, user, _client_ip(request))


@router.get("/audit", response_model=AuditListResponse)
async def admin_audit_log(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("audit:view")),
    limit: int = 100,
):
    """Return recent audit-log entries (requires audit:view)."""
    rows = (
        db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
        .scalars()
        .all()
    )
    return {"logs": audit_logs_to_dicts(db, rows), "can_purge": "audit:purge" in get_permissions_for_role(_.get("role", ""))}


@router.post("/audit/clear")
async def admin_clear_audit(
    body: AuditClearRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("audit:purge")),
):
    """Permanently delete every audit-log entry (admin only).

    This is a destructive, forensically-sensitive operation, so it is gated on
    the ``audit:purge`` permission (admin-only — *not* granted to reviewers)
    and requires an explicit ``confirm: true`` in the body.

    The purge itself is recorded as the **sole surviving entry** (action
    ``audit_clear``) so the act of wiping the log stays accountable: even an
    emptied log shows *who* cleared it and *when*.
    """
    if not body.confirm:
        raise HTTPException(400, "Confirmation required to clear audit logs")
    ip = _client_ip(request)
    count = db.execute(text("SELECT COUNT(*) FROM audit_log")).scalar() or 0
    db.execute(text("DELETE FROM audit_log"))
    db.commit()
    # Record the wipe as the only remaining entry (accountability trail).
    _audit_log(
        "audit_clear",
        target=f"cleared {count} records",
        username=user["username"],
        ip=ip,
    )
    return {"cleared": count, "cleared_by": user["username"]}


# ---------------------------------------------------------------------------
# Site / branding name (admin-only runtime rebrand)
# ---------------------------------------------------------------------------
class SiteNameRequest(BaseModel):
    name: str


@router.get("/site")
async def admin_get_site(_: dict = Depends(require_admin)):
    """Return the current site/branding display name (admin only)."""
    return {"name": config.APP_NAME}


@router.put("/site")
async def admin_set_site(
    body: SiteNameRequest,
    admin: dict = Depends(require_admin),
    request: Request = None,
):
    """Update the site/branding display name (admin only).

    Updates the running process immediately and persists to .env so the change
    survives a restart. Emits an audit log entry.
    """
    try:
        new_name, persisted = config.set_app_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_log("update_site", admin["username"], new_name, _client_ip(request))
    return {"ok": True, "name": new_name, "persisted": persisted}


# ---------------------------------------------------------------------------
# Max upload size (admin-only runtime tuning)
# ---------------------------------------------------------------------------
class UploadLimitRequest(BaseModel):
    max_upload_size_mb: int


@router.get("/upload-limit")
async def admin_get_upload_limit(_: dict = Depends(require_admin)):
    """Return the current per-file upload size cap in MB (admin only)."""
    return {"max_upload_size_mb": config.get_max_upload_size_mb()}


@router.put("/upload-limit")
async def admin_set_upload_limit(
    body: UploadLimitRequest,
    admin: dict = Depends(require_admin),
    request: Request = None,
):
    """Update the per-file upload size cap (admin only).

    Updates the running process immediately and persists to .env so the change
    survives a restart. Emits an audit log entry.
    """
    try:
        new_mb, persisted = config.set_max_upload_size_mb(body.max_upload_size_mb)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_log("update_upload_limit", admin["username"], f"{new_mb}MB", _client_ip(request))
    return {"ok": True, "max_upload_size_mb": new_mb, "persisted": persisted}


# ---------------------------------------------------------------------------
# Generic admin KV settings framework.
# Adding a new admin-tunable setting = one entry in SETTING_TYPES
# (no new endpoint, no new frontend handler). Each entry maps a UI/API key
# to its config getter/setter; the setter owns validation + persistence
# (we reuse the .env-backed helpers in config.py). The dedicated
# /api/admin/site and /api/admin/upload-limit endpoints stay for backwards
# compatibility and as thin wrappers around the same setters.
# ---------------------------------------------------------------------------
SETTING_TYPES: dict = {
    "site_name": {
        "getter": lambda: config.APP_NAME,
        "setter": config.set_app_name,
    },
    "max_upload_size_mb": {
        "getter": config.get_max_upload_size_mb,
        "setter": config.set_max_upload_size_mb,
    },
    "max_user_upload_mb": {
        "getter": config.get_max_user_upload_mb,
        "setter": config.set_max_user_upload_mb,
    },
    "upload_rate_limit": {
        "getter": config.get_upload_rate_limit,
        "setter": config.set_upload_rate_limit,
    },
}


@router.get("/setting/{key}")
async def admin_get_setting(key: str, _: dict = Depends(require_admin)):
    """Read a registered admin setting (admin only)."""
    if key not in SETTING_TYPES:
        raise HTTPException(status_code=404, detail="Unknown setting")
    return {"key": key, "value": SETTING_TYPES[key]["getter"]()}


@router.put("/setting/{key}")
async def admin_set_setting(
    key: str,
    body: dict = Body(...),
    admin: dict = Depends(require_admin),
    request: Request = None,
):
    """Update a registered admin setting (admin only)."""
    if key not in SETTING_TYPES:
        raise HTTPException(status_code=404, detail="Unknown setting")
    if "value" not in body:
        raise HTTPException(status_code=400, detail="Missing 'value'")
    try:
        _, persisted = SETTING_TYPES[key]["setter"](body["value"])
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    new_value = SETTING_TYPES[key]["getter"]()
    _audit_log("update_setting", admin["username"], f"{key}={new_value}", _client_ip(request))
    return {"ok": True, "key": key, "value": new_value, "persisted": persisted}
