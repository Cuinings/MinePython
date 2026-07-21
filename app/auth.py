# -*- coding: utf-8 -*-
"""Authentication endpoints and helpers: login, register, current_user, admin guard."""

import secrets

from fastapi import APIRouter, Header, HTTPException

from app.database import get_db
from app.models import AuthRequest, AuthResponse
from app.utils import _hash_pw, _verify_pw

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Auth dependency helpers
# ---------------------------------------------------------------------------

def get_current_user(authorization: str = Header(default="")) -> dict | None:
    """Extract current user from Bearer token. Returns user row or None."""
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    db = get_db()
    user = db.execute(
        "SELECT id, username, nickname, role, status FROM users WHERE token = ? AND status = 'active'",
        (token,),
    ).fetchone()
    db.close()
    return dict(user) if user else None


def require_admin(authorization: str = Header(default="")):
    """Require admin Bearer token. Returns admin user dict or raises 401/403."""
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=AuthResponse)
async def register(body: AuthRequest):
    """Register a new user (pending admin approval). Optionally set nickname."""
    if not body.username or not body.password:
        raise HTTPException(400, "Username and password required")
    if len(body.username) < 2:
        raise HTTPException(400, "Username too short")
    if len(body.password) < 3:
        raise HTTPException(400, "Password too short")

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (body.username,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(409, "Username already exists")

    pw_hash = _hash_pw(body.password)
    nickname = (body.nickname or "").strip() or body.username
    db.execute(
        "INSERT INTO users (username, password, nickname, role, status) VALUES (?,?,?,?,?)",
        (body.username, pw_hash, nickname, "user", "pending"),
    )
    db.commit()
    db.close()
    return AuthResponse(ok=True, message="Registration submitted, pending admin approval")


@router.post("/login", response_model=AuthResponse)
async def login(body: AuthRequest):
    """Login, returns auth token (rejected if pending approval)."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
    db.close()
    if not row or not _verify_pw(body.password, row["password"]):
        raise HTTPException(401, "Invalid username or password")
    if row["status"] == "pending":
        raise HTTPException(403, "Account pending admin approval")
    if row["status"] == "rejected":
        raise HTTPException(403, "Account has been rejected")

    token = secrets.token_hex(32)
    db2 = get_db()
    db2.execute("UPDATE users SET token = ? WHERE id = ?", (token, row["id"]))
    db2.commit()
    db2.close()
    return AuthResponse(ok=True, token=token, message="Logged in", role=row["role"], nickname=row["nickname"])
