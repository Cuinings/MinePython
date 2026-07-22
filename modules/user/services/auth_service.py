# -*- coding: utf-8 -*-
"""Auth / session business logic (ARCH-6).

Everything in here is HTTP-agnostic: token minting, expiry evaluation, session
invalidation, expired-token purging, and the in-memory login brute-force
state. The FastAPI ``Depends``/``Header`` helpers (``get_current_user``,
``require_permission`` …) stay in :mod:`modules.user.auth` because they are part
of the HTTP layer; they call into this module. Symbols reused by other routers
(``authenticate_token``, ``purge_expired_tokens``) are re-exported from
``modules.user.auth`` for backward compatibility.
"""

import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

import modules.user.config as _cfg
from modules.user.database import (
    SessionLocal,
    SessionToken,
    User,
    get_permissions_for_role,
    orm_to_dict,
)
from modules.user.utils import _audit_log, _hash_pw, _is_legacy_hash, _verify_pw


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------
def mint_token(user: User, device: str | None = None) -> str:
    """Create a fresh SessionToken row for ``user`` and return its token string."""
    token = secrets.token_hex(32)
    expires_at = ""
    if _cfg.TOKEN_TTL_HOURS and _cfg.TOKEN_TTL_HOURS > 0:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=_cfg.TOKEN_TTL_HOURS)
        ).strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as db:
        db.add(
            SessionToken(
                user_id=user.id, token=token, expires_at=expires_at, device=device
            )
        )
        db.commit()
    return token


def _expire_clause():
    """Return a SQLAlchemy predicate that is True only for non-expired tokens.

    Tokens with an empty ``expires_at`` (TTL disabled) are treated as eternal.
    Must use ``or_()`` — a plain Python ``or`` on two ClauseElements silently
    collapses to just the second operand (SQLAlchemy footgun).
    """
    if not _cfg.TOKEN_TTL_HOURS or _cfg.TOKEN_TTL_HOURS <= 0:
        return None
    return or_(
        SessionToken.expires_at == "",
        SessionToken.expires_at > func.datetime("now"),
    )


def purge_expired_tokens() -> int:
    """Delete token rows whose ``expires_at`` is in the past (ARCH-3).

    No-op when TTL is disabled (all tokens are eternal). Returns the number of
    rows removed. Safe to call repeatedly (startup + periodic sweep).
    """
    if not _cfg.TOKEN_TTL_HOURS or _cfg.TOKEN_TTL_HOURS <= 0:
        return 0
    with SessionLocal() as db:
        result = db.execute(
            delete(SessionToken).where(
                SessionToken.expires_at != "",
                SessionToken.expires_at <= func.datetime("now"),
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def authenticate_token(raw_token: str | None) -> dict | None:
    """Resolve a raw token string to a user dict via the SessionToken table.

    Validates: token exists, its owner is ``active``, and it has not expired.
    """
    if not raw_token:
        return None
    expire = _expire_clause()
    with SessionLocal() as db:
        stmt = (
            select(User)
            .join(SessionToken, SessionToken.user_id == User.id)
            .where(SessionToken.token == raw_token, User.status == "active")
        )
        if expire is not None:
            stmt = stmt.where(expire)
        user = db.execute(stmt).scalar_one_or_none()
    if not user:
        return None
    data = orm_to_dict(user)
    data.pop("password", None)  # never expose the hash
    data.pop("password_plain", None)  # never expose the recoverable copy
    return data


def invalidate_user_sessions(db: Session, user_id: int) -> None:
    """Drop every session token for a user (forces re-login on all devices)."""
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))


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

    token = mint_token(user, device=device)
    _audit_log("login", user.username, user.username, ip)

    perms = sorted(get_permissions_for_role(user.role))
    return {
        "ok": True,
        "token": token,
        "message": "Logged in",
        "role": user.role,
        "nickname": user.nickname,
        "permissions": perms,
        "require_password_change": getattr(user, "force_pw_change", False),
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
