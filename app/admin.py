# -*- coding: utf-8 -*-
"""Admin endpoints: user CRUD, approval, pending count."""

from fastapi import APIRouter, Header, HTTPException

from app.auth import require_admin
from app.database import get_db
from app.models import AdminUserRequest
from app.utils import _hash_pw

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users")
async def admin_list_users(authorization: str = Header(default="")):
    """List all users (admin only). Returns nickname and password hash."""
    require_admin(authorization)
    db = get_db()
    rows = db.execute(
        "SELECT id, username, nickname, password, role, status, created_at FROM users ORDER BY id"
    ).fetchall()
    db.close()
    return {"users": [dict(r) for r in rows]}


@router.put("/users/{user_id}/approve")
async def admin_approve_user(user_id: int, authorization: str = Header(default="")):
    """Approve a pending user (admin only)."""
    require_admin(authorization)
    db = get_db()
    db.execute("UPDATE users SET status = 'active' WHERE id = ? AND status = 'pending'", (user_id,))
    if db.total_changes == 0:
        db.close()
        raise HTTPException(404, "User not found or not pending")
    db.commit()
    db.close()
    return {"ok": True, "message": "User approved"}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: int, authorization: str = Header(default="")):
    """Delete a user (admin only, cannot delete self)."""
    admin = require_admin(authorization)
    db = get_db()
    user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        db.close()
        raise HTTPException(404, "User not found")
    if str(user["id"]) == str(admin["id"]):
        db.close()
        raise HTTPException(400, "Cannot delete your own account")
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    db.close()
    return {"ok": True, "message": f"User '{user['username']}' deleted"}


@router.post("/users")
async def admin_create_user(body: AdminUserRequest, authorization: str = Header(default="")):
    """Create a new user (admin only). Can set all fields."""
    require_admin(authorization)
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
    role = body.role if body.role in ("admin", "user") else "user"
    status = body.status if body.status in ("active", "pending") else "active"
    db.execute(
        "INSERT INTO users (username, password, nickname, role, status) VALUES (?,?,?,?,?)",
        (body.username, pw_hash, nickname, role, status),
    )
    db.commit()
    db.close()
    return {"ok": True, "message": f"User '{body.username}' created"}


@router.put("/users/{user_id}")
async def admin_update_user(user_id: int, body: AdminUserRequest, authorization: str = Header(default="")):
    """Modify user info (admin only). All fields optional except username."""
    require_admin(authorization)
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        db.close()
        raise HTTPException(404, "User not found")

    updates = []
    params = []

    if body.username and body.username != user["username"]:
        if len(body.username) < 2:
            db.close()
            raise HTTPException(400, "Username too short")
        conflict = db.execute(
            "SELECT id FROM users WHERE username = ? AND id != ?", (body.username, user_id)
        ).fetchone()
        if conflict:
            db.close()
            raise HTTPException(409, "Username already exists")
        updates.append("username = ?")
        params.append(body.username)

    if body.password:
        if len(body.password) < 3:
            db.close()
            raise HTTPException(400, "Password too short")
        pw_hash = _hash_pw(body.password)
        updates.append("password = ?")
        params.append(pw_hash)

    if body.nickname is not None and body.nickname.strip():
        updates.append("nickname = ?")
        params.append(body.nickname.strip())

    if body.role and body.role in ("admin", "user"):
        updates.append("role = ?")
        params.append(body.role)

    if body.status and body.status in ("active", "pending"):
        updates.append("status = ?")
        params.append(body.status)

    if not updates:
        db.close()
        return {"ok": True, "message": "No changes"}

    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    db.close()
    return {"ok": True, "message": "User updated"}


@router.get("/pending")
async def admin_pending_count(authorization: str = Header(default="")):
    """Get pending user count and list (admin only, lightweight)."""
    require_admin(authorization)
    db = get_db()
    rows = db.execute(
        "SELECT id, username FROM users WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    db.close()
    return {"count": len(rows), "users": [dict(r) for r in rows]}
