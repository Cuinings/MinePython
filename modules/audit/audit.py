# -*- coding: utf-8 -*-
"""Public audit-log endpoint.

This is the dedicated audit entry point (``/audit.html``) that is visible to
*every authenticated user*, separate from the admin-only ``/api/admin/audit``
used inside the admin console.

Access rules (enforced server-side, never by the client):

* **Anonymous (unauthenticated)** callers are rejected with ``401``.
* **Regular users** (``user`` / ``uploader``) see **only their own** records.
  Their username is forced into the query; any ``user`` filter they send is
  ignored (defence in depth).
* **Admins and reviewers** (holding ``audit:view``) see **all** records, with
  an optional ``user`` filter to narrow by a specific account.

The response includes ``scope`` (``"self"`` / ``"all"``) and ``can_view_all``
so the UI can render the correct controls without re-deriving permissions.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select

from modules.user.auth import get_permissions_for_role, require_permission
from modules.user.database import AuditLog, get_db, orm_to_dict

router = APIRouter(prefix="/api/audit", tags=["Audit"])

MAX_PAGE_SIZE = 200


@router.get("/logs")
async def audit_logs(
    db=Depends(get_db),
    user: dict = Depends(require_permission("audit:view_self")),
    page: int = 1,
    page_size: int = 50,
    action: str = "",
    search: str = "",
    user_filter: str = "",
):
    """Return audit-log entries scoped to the caller's permissions.

    Regular users are hard-scoped to their own rows; admins/reviewers see all
    (optionally filtered by ``user_filter``).
    """
    perms = get_permissions_for_role(user["role"])
    can_view_all = "audit:view" in perms
    scope = "all" if can_view_all else "self"

    stmt = select(AuditLog)
    # Server-side scoping: regular users can NEVER see other accounts, no
    # matter what the client sends. Only audit:view holders may narrow by user.
    if not can_view_all:
        stmt = stmt.where(AuditLog.username == user["username"])
    elif user_filter:
        stmt = stmt.where(AuditLog.username == user_filter)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if search:
        stmt = stmt.where(AuditLog.target.like(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    rows = db.execute(
        stmt.order_by(AuditLog.id.desc()).limit(page_size).offset(offset)
    ).scalars().all()

    return {
        "logs": [orm_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "scope": scope,
        "can_view_all": can_view_all,
    }
