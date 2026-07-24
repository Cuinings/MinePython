# -*- coding: utf-8 -*-
"""Admin endpoints: user CRUD, approval, pending count, audit log (RBAC-gated).

The user business logic has moved to :mod:`modules.user.services.user_service`;
the handlers here do permission guarding + request/response shaping and delegate
the actual work to the service.

The orphan-cleanup endpoint (``POST /api/admin/cleanup``) has been relocated to
the file-server module (:mod:`modules.files.cleanup`) so that this user module
stays free of any reverse dependency on the files module.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.user.auth import get_current_user, require_admin, require_permission
from modules.user.database import AuditLog, User, get_db, orm_to_dict
from modules.user.models import (
    AdminBatchRequest,
    AdminUserRequest,
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
            select(User.id, User.username)
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
    return {"logs": [orm_to_dict(r) for r in rows]}


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
        new_name = config.set_app_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_log("update_site", admin["username"], new_name, _client_ip(request))
    return {"ok": True, "name": new_name}
