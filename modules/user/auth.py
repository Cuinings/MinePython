# -*- coding: utf-8 -*-
"""Authentication endpoints and HTTP-layer helpers: login, register, logout,
current_user, RBAC guards.

The business logic (token lifecycle, login brute-force state, login
orchestration, self-service password/deactivate) lives in
:mod:`modules.user.services.auth_service` and
:mod:`modules.user.services.user_service`; this module keeps the FastAPI
``Depends``/``Header`` plumbing and the route handlers, which delegate to the
services. ``authenticate_token`` and ``purge_expired_tokens`` are re-exported
here so existing imports keep resolving.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from modules.user.config import ADMIN_USERNAME
from modules.user.database import SessionToken, User, get_db, get_permissions_for_role
from modules.user.models import (
    AuthRequest,
    AuthResponse,
    DeactivateRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
)
from modules.user.services import user_service
from modules.user.services.auth_service import (
    authenticate_token,
    clear_ip_failures as _clear_ip_failures,
    clear_login_failures as _clear_login_failures,
    ip_throttled as _ip_throttled,
    login_locked as _login_locked,
    login_user,
    purge_expired_tokens,
    register_ip_failure as _register_ip_failure,
    register_login_failure as _register_login_failure,
)
from modules.user.utils import _audit_log, _client_ip

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Auth & RBAC dependency helpers (HTTP layer — stay in the router module)
# ---------------------------------------------------------------------------
def get_current_user(authorization: str = Header(default="")) -> dict | None:
    """Extract current user from a Bearer token header. Returns a user dict or None."""
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else None
    return authenticate_token(token)


def require_admin(authorization: str = Header(default="")) -> dict:
    """Require an admin Bearer token. Raises 401/403 otherwise."""
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def require_permission(permission: str):
    """Build a dependency that requires ``permission`` for the current user."""

    def _dep(authorization: str = Header(default="")) -> dict:
        user = get_current_user(authorization)
        if not user:
            raise HTTPException(401, "Authentication required")
        if permission not in get_permissions_for_role(user["role"]):
            raise HTTPException(403, f"Permission '{permission}' required")
        return user

    return _dep


def require_permission_allow_anonymous(permission: str):
    """Like :func:`require_permission`, but lets unauthenticated (anonymous)
    callers through *only* when ``permission`` is part of the ``anonymous``
    role's grant (read-only browsing).

    Used by the "enter as anonymous" guest mode: ``file:list`` and
    ``file:download`` are safe to expose read-only, while every write / admin
    endpoint uses :func:`require_permission` and therefore still requires a
    real session token. Anonymous is represented by a synthetic user dict so
    downstream code that inspects ``user["role"]`` behaves correctly.
    """

    def _dep(authorization: str = Header(default="")) -> dict:
        user = get_current_user(authorization)
        if not user:
            if permission in get_permissions_for_role("anonymous"):
                return {"role": "anonymous", "username": "anonymous", "anonymous": True}
            raise HTTPException(401, "Authentication required")
        if permission not in get_permissions_for_role(user["role"]):
            raise HTTPException(403, f"Permission '{permission}' required")
        return user

    return _dep


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/register", response_model=AuthResponse)
async def register(
    body: AuthRequest, db: Session = Depends(get_db), request: Request = None
):
    """Register a new user (pending admin approval). Optionally set nickname."""
    ip = _client_ip(request)
    result = user_service.register_user(db, body.username, body.password, body.nickname, ip)
    return AuthResponse(**result)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: AuthRequest, db: Session = Depends(get_db), request: Request = None
):
    """Login, mints a fresh independent session token (rejected if pending)."""
    ip = _client_ip(request)
    result = login_user(db, body.username, body.password, ip, device=body.nickname or "")
    return AuthResponse(**result)


@router.post("/logout")
async def logout(
    authorization: str = Header(default=""),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Invalidate the current session token (does not affect other sessions)."""
    if not user:
        raise HTTPException(401, "Authentication required")
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else None
    if not token:
        raise HTTPException(401, "Authentication required")
    db.execute(delete(SessionToken).where(SessionToken.token == token))
    db.commit()
    _audit_log("logout", user["username"], user["username"], _client_ip(request))
    return {"ok": True, "message": "Logged out"}


@router.get("/me")
async def me(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Return the current user's profile and effective permissions.

    Also refreshes ``last_login_ip`` from the current request so the profile and
    admin list reflect the most recent source IP without requiring a fresh login.
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")

    shown_ip = user.get("last_login_ip", "") or ""
    ip = _client_ip(request)
    if ip:
        try:
            target = db.execute(
                select(User).where(User.id == user["id"])
            ).scalar_one_or_none()
            if target is not None:
                if target.last_login_ip != ip:
                    target.last_login_ip = ip
                    db.commit()
                shown_ip = target.last_login_ip
        except Exception:
            db.rollback()

    return {
        "ok": True,
        "username": user["username"],
        "nickname": user["nickname"],
        "role": user["role"],
        "status": user["status"],
        "is_default": bool(user.get("is_default", False)),
        "admin_username": ADMIN_USERNAME,
        "last_login_ip": shown_ip or "",
        "permissions": sorted(get_permissions_for_role(user["role"])),
    }


@router.put("/me/password", response_model=AuthResponse)
async def change_my_password(
    body: PasswordChangeRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Change the caller's own password. Requires the current password; invalidates all sessions."""
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)
    result = user_service.change_password(db, user["id"], body.old_password, body.new_password, ip)
    return AuthResponse(**result)


@router.post("/me/deactivate", response_model=AuthResponse)
async def deactivate_my_account(
    body: DeactivateRequest | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Deactivate (注销) the caller's own account. Default admin is protected."""
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)
    result = user_service.deactivate_user(db, user["id"], ip)
    return AuthResponse(**result)


@router.put("/me")
async def update_my_profile(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Update the caller's own profile (nickname, optional password change).

    Any authenticated user may use this — it only touches the caller's own
    row, never other accounts. Changing the password invalidates all sessions.
    """
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)
    result = user_service.update_own_profile(
        db, user["id"], body.nickname, body.old_password, body.new_password, ip
    )
    return result
