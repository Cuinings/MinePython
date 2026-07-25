# -*- coding: utf-8 -*-
"""Authentication endpoints and HTTP-layer helpers: login, register, logout,
current_user, RBAC guards.

The business logic (JWT lifecycle, login brute-force state, login
orchestration, self-service password/deactivate) lives in
:mod:`modules.user.services.auth_service` and
:mod:`modules.user.services.user_service`; this module keeps the FastAPI
``Depends``/``Header`` plumbing and the route handlers, which delegate to the
services. ``authenticate_token`` and ``purge_expired_tokens`` are re-exported
here so existing imports keep resolving.

ARCH-9/10: blocking DB work runs inside ``run_in_threadpool`` (the sync
SQLAlchemy engine + psycopg3 driver stay unchanged) so the async event loop is
never blocked by a DB round-trip; the hot path (access-token verification) is
fully stateless and never touches the DB. Each request opens its own session
*within* the threadpool task, so a single ``Session`` is never shared across
threads — which keeps the sync SQLAlchemy usage correct under concurrency.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select

from modules.user.config import ADMIN_USERNAME, JWT_REFRESH_TTL_DAYS, REFRESH_TOKEN_IN_COOKIE
from modules.user.database import PERMISSIONS, SessionLocal, User, get_permissions_for_role
from modules.user.models import (
    AuthRequest,
    AuthResponse,
    DeactivateRequest,
    LogoutRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
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
    refresh_session,
    register_ip_failure as _register_ip_failure,
    register_login_failure as _register_login_failure,
    revoke_refresh_token,
)
from modules.user.utils import _audit_log, _client_ip

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Cookie name for the optional httpOnly refresh token (REFRESH_TOKEN_IN_COOKIE).
_REFRESH_COOKIE = "fs_refresh"


def _cookie_secure(request: Request | None) -> bool:
    """Only mark the refresh cookie Secure when served over HTTPS."""
    return bool(request and getattr(request, "url", None) and request.url.scheme == "https")


def _set_refresh_cookie(resp, raw: str, request: Request | None) -> None:
    resp.set_cookie(
        _REFRESH_COOKIE,
        raw,
        httponly=True,
        samesite="strict",
        secure=_cookie_secure(request),
        path="/api/auth",
        max_age=int(JWT_REFRESH_TTL_DAYS) * 86400,
    )


def _clear_refresh_cookie(resp) -> None:
    resp.delete_cookie(_REFRESH_COOKIE, path="/api/auth")


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
async def register(body: AuthRequest, request: Request = None):
    """Register a new user (pending admin approval). Optionally set nickname."""
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            return user_service.register_user(db, body.username, body.password, body.nickname, ip)

    result = await run_in_threadpool(_work)
    return AuthResponse(**result)


@router.post("/login", response_model=AuthResponse)
async def login(body: AuthRequest, request: Request = None):
    """Login: mints a fresh access JWT + a hashed refresh token (rejected if pending)."""
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            return login_user(db, body.username, body.password, ip, device=body.nickname or "")

    result = await run_in_threadpool(_work)
    refresh = result.get("refresh_token")
    if REFRESH_TOKEN_IN_COOKIE:
        # Hand the refresh token to the browser as an httpOnly cookie; do NOT
        # echo it in the JSON body (XSS can't read it). The access token still
        # lives in localStorage and is sent as a Bearer header.
        out = dict(result)
        out["refresh_in_cookie"] = True
        out["refresh_token"] = None
        resp = JSONResponse(out)
        _set_refresh_cookie(resp, refresh, request)
        return resp
    return AuthResponse(**result)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(body: RefreshRequest, request: Request = None):
    """Exchange a still-valid refresh token for a new access token (with rotation)."""
    ip = _client_ip(request)
    raw = body.refresh_token
    if REFRESH_TOKEN_IN_COOKIE:
        # Cookie takes precedence when present (the browser sends it automatically).
        raw = (request.cookies.get(_REFRESH_COOKIE) if request else None) or raw

    def _work():
        with SessionLocal() as db:
            return refresh_session(db, raw, device=body.device or "")

    try:
        result = await run_in_threadpool(_work)
    except HTTPException as e:
        if REFRESH_TOKEN_IN_COOKIE:
            resp = JSONResponse({"ok": False, "message": e.detail}, status_code=e.status_code)
            _clear_refresh_cookie(resp)
            return resp
        raise

    if REFRESH_TOKEN_IN_COOKIE:
        out = dict(result)
        out["refresh_in_cookie"] = True
        out["refresh_token"] = None
        resp = JSONResponse(out)
        _set_refresh_cookie(resp, result["refresh_token"], request)
        return resp
    return AuthResponse(**result)


@router.post("/logout")
async def logout(
    authorization: str = Header(default=""),
    body: LogoutRequest | None = None,
    request: Request = None,
):
    """Invalidate the current refresh token so the session cannot be renewed.

    The access JWT is stateless and expires on its own (ARCH-9 trade-off); we
    revoke the refresh token here so a stolen/leaked refresh token is dead and
    the client is forced to re-authenticate after the access token lapses.
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    refresh = body.refresh_token if body else None
    if REFRESH_TOKEN_IN_COOKIE:
        refresh = refresh or (request.cookies.get(_REFRESH_COOKIE) if request else None)
    if refresh:

        def _work():
            with SessionLocal() as db:
                revoke_refresh_token(db, refresh)

        await run_in_threadpool(_work)
    _audit_log("logout", user["username"], user["username"], _client_ip(request))
    resp = JSONResponse({"ok": True, "message": "Logged out"})
    if REFRESH_TOKEN_IN_COOKIE:
        _clear_refresh_cookie(resp)
    return resp


@router.get("/me")
async def me(authorization: str = Header(default=""), request: Request = None):
    """Return the current user's profile and effective permissions.

    Also refreshes ``last_login_ip`` from the current request so the profile and
    admin list reflect the most recent source IP without requiring a fresh login.
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            shown_ip = user.get("last_login_ip", "") or ""
            target = db.execute(select(User).where(User.id == user["id"])).scalar_one_or_none()
            if target is not None:
                if ip and target.last_login_ip != ip:
                    target.last_login_ip = ip
                    db.commit()
                shown_ip = target.last_login_ip
            # Prefer the LIVE DB row over the JWT claims so a nickname / role /
            # status change is reflected immediately (claims only refresh on the
            # next login / refresh). The claims are the fallback if the row is
            # somehow missing.
            live_nick = target.nickname if target is not None else user["nickname"]
            live_role = target.role if target is not None else user["role"]
            live_status = target.status if target is not None else user["status"]
            perms = sorted(get_permissions_for_role(user["role"]))
            return {
                "ok": True,
                "username": user["username"],
                "nickname": live_nick,
                "role": live_role,
                "status": live_status,
                "is_default": bool(user.get("is_default", False)),
                "admin_username": ADMIN_USERNAME,
                "last_login_ip": shown_ip or "",
                "permissions": perms,
                "permission_names": [PERMISSIONS.get(p, p) for p in perms],
            }

    return await run_in_threadpool(_work)


@router.put("/me/password", response_model=AuthResponse)
async def change_my_password(
    body: PasswordChangeRequest,
    authorization: str = Header(default=""),
    request: Request = None,
):
    """Change the caller's own password. Requires the current password; invalidates all sessions."""
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            return user_service.change_password(db, user["id"], body.old_password, body.new_password, ip)

    result = await run_in_threadpool(_work)
    return AuthResponse(**result)


@router.post("/me/deactivate", response_model=AuthResponse)
async def deactivate_my_account(
    body: DeactivateRequest | None = None,
    authorization: str = Header(default=""),
    request: Request = None,
):
    """Deactivate (注销) the caller's own account. Default admin is protected."""
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            return user_service.deactivate_user(db, user["id"], ip)

    result = await run_in_threadpool(_work)
    return AuthResponse(**result)


@router.put("/me")
async def update_my_profile(
    body: ProfileUpdateRequest,
    authorization: str = Header(default=""),
    request: Request = None,
):
    """Update the caller's own profile (nickname, optional password change).

    Any authenticated user may use this — it only touches the caller's own
    row, never other accounts. Changing the password invalidates all sessions.
    """
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    ip = _client_ip(request)

    def _work():
        with SessionLocal() as db:
            return user_service.update_own_profile(
                db, user["id"], body.nickname, body.old_password, body.new_password, ip
            )

    result = await run_in_threadpool(_work)
    return result
