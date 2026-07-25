# -*- coding: utf-8 -*-
"""Auth / session business logic (ARCH-6, ARCH-9).

Everything in here is HTTP-agnostic: JWT access-token minting/decoding, refresh
token lifecycle, session invalidation, expired-token purging, and the in-memory
login brute-force state. The FastAPI ``Depends``/``Header`` helpers
(``get_current_user``, ``require_permission`` …) stay in
:mod:`modules.user.auth` because they are part of the HTTP layer; they call into
this module. Symbols reused by other routers (``authenticate_token``,
``purge_expired_tokens``) are re-exported from ``modules.user.auth`` for
backward compatibility.

ARCH-9 model:
* **access token** — a short-lived, signed **JWT**. Verified by signature only
  (:func:`authenticate_token` / :func:`decode_access_token`) — NO database hit —
  which is what makes the hot path stateless and horizontally scalable.
* **refresh token** — an opaque random string whose **SHA-256 hash** is stored
  in the ``refresh_tokens`` table (replacing the old self-built ``tokens``
  table). Consulted only on the infrequent /api/auth/refresh call, so logout /
  password-change can still revoke sessions immediately.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import modules.user.config as _cfg
from modules.user.database import (
    RefreshToken,
    SessionLocal,
    User,
    get_permissions_for_role,
)
from modules.user.utils import _audit_log, _hash_pw, _is_legacy_hash, _now_str, _verify_pw


# ---------------------------------------------------------------------------
# Access token (stateless JWT) — no DB, verified by signature
# ---------------------------------------------------------------------------
def _user_claims(user: User) -> dict:
    """Build the identity claims embedded in an access JWT.

    These are what :func:`authenticate_token` reconstructs a user dict from, so
    every field the app reads off ``user[...]`` in a guard/handler must live
    here. Mutable-but-rarely-changing fields (nickname/role) are refreshed on
    the next token refresh; endpoints needing live data (e.g. /me) re-read the DB.
    """
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "nickname": user.nickname,
        "status": user.status,
        "is_default": bool(getattr(user, "is_default", False)),
    }


def mint_access_token(user: User) -> tuple[str, int]:
    """Sign a short-lived access JWT for ``user``. Returns ``(token, ttl_secs)``."""
    ttl = max(1, _cfg.JWT_ACCESS_TTL_MINUTES) * 60
    now = datetime.now(timezone.utc)
    payload = {
        **_user_claims(user),
        "sub": str(user.id),
        "type": "access",
        "iss": _cfg.JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, _cfg.JWT_SECRET, algorithm=_cfg.JWT_ALGORITHM)
    # PyJWT<2 returned bytes; normalize to str for consistent transport.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token, ttl


def decode_access_token(raw_token: str | None) -> dict | None:
    """Verify an access JWT by signature + expiry. Returns claims or None."""
    if not raw_token:
        return None
    try:
        claims = jwt.decode(
            raw_token,
            _cfg.JWT_SECRET,
            algorithms=[_cfg.JWT_ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("type") != "access":
        return None
    return claims


def authenticate_token(raw_token: str | None) -> dict | None:
    """Resolve a raw access token to a user dict — STATELESS, no DB (ARCH-9).

    Backward-compatible name: the file/download endpoints and the HTTP-layer
    ``get_current_user`` still call this. It now verifies a JWT signature
    instead of joining the tokens table, eliminating the per-request DB hit.
    """
    claims = decode_access_token(raw_token)
    if not claims:
        return None
    return {
        "id": claims.get("id"),
        "username": claims.get("username"),
        "role": claims.get("role"),
        "nickname": claims.get("nickname", ""),
        "status": claims.get("status", "active"),
        "is_default": bool(claims.get("is_default", False)),
    }


# ---------------------------------------------------------------------------
# Refresh token (server-side, hashed) — the only persisted auth state
# ---------------------------------------------------------------------------
def _hash_refresh(raw_token: str) -> str:
    """SHA-256 the raw refresh token for at-rest storage (never store raw)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mint_refresh_token(db: Session, user: User, device: str | None = None) -> str:
    """Create a refresh_tokens row for ``user`` and return the RAW token string.

    Only the hash is persisted; the raw value is returned to the client once.
    """
    raw = secrets.token_urlsafe(48)
    expires_at = (
        datetime.now() + timedelta(days=max(1, _cfg.JWT_REFRESH_TTL_DAYS))
    ).strftime("%Y-%m-%d %H:%M:%S")
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_refresh(raw),
            expires_at=expires_at,
            device=device or None,
        )
    )
    db.commit()
    return raw


def _find_valid_refresh(db: Session, raw_token: str) -> RefreshToken | None:
    """Return the non-expired refresh row for ``raw_token``, or None."""
    if not raw_token:
        return None
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(raw_token))
    ).scalar_one_or_none()
    if row is None:
        return None
    # expires_at is an ISO-ish local string ("YYYY-MM-DD HH:MM:SS"), which sorts
    # lexicographically — so a plain string compare is a correct, cross-DB
    # expiry check without any dialect-specific SQL date functions.
    if row.expires_at and row.expires_at <= _now_str():
        return None
    return row


def revoke_refresh_token(db: Session, raw_token: str) -> int:
    """Delete a single refresh row (logout of one session). Returns rows removed."""
    if not raw_token:
        return 0
    result = db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == _hash_refresh(raw_token))
    )
    db.commit()
    return int(result.rowcount or 0)


def refresh_session(db: Session, raw_refresh: str, device: str = "") -> dict:
    """Exchange a valid refresh token for a new access token (with rotation).

    Rotation: the presented refresh token is invalidated and a fresh one is
    issued, so a leaked/replayed refresh token has a limited window. Raises
    ``HTTPException(401)`` when the refresh token is missing/expired/revoked.
    """
    row = _find_valid_refresh(db, raw_refresh)
    if row is None:
        raise HTTPException(401, "Invalid or expired refresh token")
    user = db.execute(select(User).where(User.id == row.user_id)).scalar_one_or_none()
    if user is None or user.status != "active":
        # Owner gone or no longer active — drop the row and reject.
        db.execute(delete(RefreshToken).where(RefreshToken.id == row.id))
        db.commit()
        raise HTTPException(401, "Account is not active")

    # Rotate: remove the used refresh token, mint a fresh pair.
    db.execute(delete(RefreshToken).where(RefreshToken.id == row.id))
    db.commit()
    access, ttl = mint_access_token(user)
    new_refresh = mint_refresh_token(db, user, device=device or row.device or "")
    perms = sorted(get_permissions_for_role(user.role))
    return {
        "ok": True,
        "token": access,            # back-compat alias
        "access_token": access,
        "refresh_token": new_refresh,
        "expires_in": ttl,
        "message": "Token refreshed",
        "role": user.role,
        "nickname": user.nickname,
        "permissions": perms,
        "is_default": bool(getattr(user, "is_default", False)),
        "admin_username": _cfg.ADMIN_USERNAME,
    }


def purge_expired_tokens() -> int:
    """Delete expired refresh_tokens rows (ARCH-3). Returns rows removed.

    Cross-DB: compares the stored local-time string against ``_now_str()`` via a
    plain string comparison (the format sorts lexicographically), so no
    SQLite-only ``datetime()`` SQL is used and it works on Postgres too.
    """
    now = _now_str()
    with SessionLocal() as db:
        result = db.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at != "",
                RefreshToken.expires_at <= now,
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def invalidate_user_sessions(db: Session, user_id: int) -> None:
    """Drop every refresh token for a user (forces re-login on all devices)."""
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))


def login_user(db: Session, username: str, password: str, ip: str, device: str = "") -> dict:
    """Authenticate a login attempt and mint a fresh session token.

    Encapsulates the full login orchestration that used to live in the route
    handler: dual rate-limiting, credential check, legacy-hash upgrade, session
    minting and permission resolution. Raises ``HTTPException`` (401/403/429)
    on failure. Returns the API payload dict on success.
    """
    ip_wait = ip_throttled(ip)
    if ip_wait > 0:
        raise HTTPException(429, f"操作过于频繁，请于 {ip_wait} 秒后重试")

    locked = login_locked(username)
    if locked > 0:
        raise HTTPException(429, f"账户已锁定，请于 {locked} 秒后重试")

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not _verify_pw(password, user.password):
        register_ip_failure(ip)
        if user is not None:
            rem = register_login_failure(username)
            if rem > 0:
                raise HTTPException(429, f"账户已锁定，请于 {rem} 秒后重试")
        _audit_log("login_fail", username, username, ip)
        raise HTTPException(401, "Invalid username or password")
    if user.status == "pending":
        raise HTTPException(403, "Account pending admin approval")
    if user.status == "rejected":
        raise HTTPException(403, "Account has been rejected")
    if user.status == "deactivated":
        raise HTTPException(403, "Account has been deactivated")

    if _is_legacy_hash(user.password):
        user.password = _hash_pw(password)
        db.commit()

    clear_login_failures(username)
    clear_ip_failures(ip)

    # Record the source IP of this successful login so it can be surfaced in the
    # user's own profile and the admin user-management list.
    user.last_login_ip = ip
    db.commit()

    # ARCH-9: mint a stateless access JWT + a server-side (hashed) refresh token.
    access, ttl = mint_access_token(user)
    refresh = mint_refresh_token(db, user, device=device)
    _audit_log("login", user.username, user.username, ip)

    perms = sorted(get_permissions_for_role(user.role))
    return {
        "ok": True,
        "token": access,            # back-compat alias (existing clients/tests)
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": ttl,
        "message": "Logged in",
        "role": user.role,
        "nickname": user.nickname,
        "permissions": perms,
        "require_password_change": getattr(user, "force_pw_change", False),
        "is_default": bool(getattr(user, "is_default", False)),
        "admin_username": _cfg.ADMIN_USERNAME,
    }


# ---------------------------------------------------------------------------
# Login brute-force protection (in-memory, single-process). Two dimensions:
#   1. Per-username lock (ARCH/P0-3)
#   2. Per-IP throttle (ARCH-2)
# ---------------------------------------------------------------------------
_LOGIN_FAILS: dict[str, dict] = {}
_LOGIN_IP_FAILS: dict[str, dict] = {}


def login_locked(username: str) -> int:
    """Return seconds left until the username unlocks, or 0 if not locked."""
    rec = _LOGIN_FAILS.get(username)
    if not rec:
        return 0
    remaining = rec.get("until", 0) - time.time()
    return int(remaining) if remaining > 0 else 0


def register_login_failure(username: str) -> int:
    """Record a failed login; returns seconds left if now locked, else 0."""
    rec = _LOGIN_FAILS.setdefault(username, {"count": 0, "until": 0})
    rec["count"] += 1
    if rec["count"] > _cfg.MAX_LOGIN_FAILS:
        rec["until"] = time.time() + _cfg.LOGIN_LOCK_SECONDS
        return _cfg.LOGIN_LOCK_SECONDS
    return 0


def clear_login_failures(username: str) -> None:
    """Reset failure tracking after a successful login."""
    _LOGIN_FAILS.pop(username, None)


def ip_throttled(ip: str) -> int:
    """Return seconds left until an IP's throttle window clears, or 0."""
    if not ip:
        return 0
    rec = _LOGIN_IP_FAILS.get(ip)
    if not rec:
        return 0
    elapsed = time.time() - rec["window_start"]
    if elapsed > _cfg.LOGIN_IP_WINDOW_SECONDS:
        _LOGIN_IP_FAILS.pop(ip, None)
        return 0
    if rec["count"] > _cfg.LOGIN_IP_MAX_FAILS:
        return int(_cfg.LOGIN_IP_WINDOW_SECONDS - elapsed) or 1
    return 0


def register_ip_failure(ip: str) -> None:
    """Record a failed login attempt from ``ip`` within the sliding window."""
    if not ip:
        return
    now = time.time()
    rec = _LOGIN_IP_FAILS.get(ip)
    if not rec or now - rec["window_start"] > _cfg.LOGIN_IP_WINDOW_SECONDS:
        _LOGIN_IP_FAILS[ip] = {"count": 1, "window_start": now}
    else:
        rec["count"] += 1


def clear_ip_failures(ip: str) -> None:
    """Reset a client IP's throttle after a successful login."""
    if ip:
        _LOGIN_IP_FAILS.pop(ip, None)
