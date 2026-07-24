# -*- coding: utf-8 -*-
"""User / account business logic (ARCH-6).

Encapsulates the DB operations behind the admin user-CRUD endpoints and the
self-service password/deactivate endpoints. Route handlers in
:mod:`modules.user.admin` (and :mod:`modules.user.auth` for the self-service
ones) keep the ``Depends`` permission guards and response shaping, but delegate
the actual work here. Functions raise ``HTTPException`` for domain errors so the
HTTP layer stays thin.
"""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from modules.user.config import ADMIN_USERNAME
from modules.user.database import (
    ROLES,
    SessionToken,
    User,
    get_permissions_for_role,
    orm_to_dict,
)
from modules.user.models import AdminBatchRequest, AdminUserRequest
from modules.user.utils import (
    _audit_log,
    _client_ip,
    _decrypt_plain,
    _encrypt_plain,
    _hash_pw,
    _verify_pw,
)


def user_to_dict(user) -> dict:
    """Convert an ORM User instance to the API representation."""
    d = orm_to_dict(user)
    d["password_plain"] = _decrypt_plain(d.get("password_plain", ""))
    return d


def _is_bootstrap_admin(user) -> bool:
    """Return True if the user is the built-in bootstrap admin account.

    Uses the DB ``is_default`` flag as the primary signal, but falls back to
    matching the configured ``ADMIN_USERNAME``. This protects legacy databases
    where the flag may not have been backfilled yet.
    """
    return bool(getattr(user, "is_default", False) or user.username == ADMIN_USERNAME)


def invalidate_user_tokens(db: Session, user_id: int) -> None:
    """Drop every session token for a user (forces re-login on all devices)."""
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))


def register_user(db: Session, username: str, password: str, nickname: str, ip: str) -> dict:
    """Register a new user (pending admin approval). Returns an API dict."""
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if len(username) < 2:
        raise HTTPException(400, "Username too short")
    if len(password) < 3:
        raise HTTPException(400, "Password too short")

    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Username already exists")

    nick = (nickname or "").strip() or username
    db.add(
        User(
            username=username,
            password=_hash_pw(password),
            password_plain=_encrypt_plain(password),
            nickname=nick,
            role="user",
            status="pending",
        )
    )
    db.commit()
    _audit_log("register", username, username, ip)
    return {
        "ok": True,
        "message": "Registration submitted, pending admin approval",
        "is_default": False,
    }


def create_user(db: Session, body: AdminUserRequest, ip: str) -> dict:
    """Create a new user (admin). Returns an API dict."""
    if not body.username or not body.password:
        raise HTTPException(400, "Username and password required")
    if len(body.username) < 2:
        raise HTTPException(400, "Username too short")
    if len(body.password) < 3:
        raise HTTPException(400, "Password too short")

    existing = db.execute(
        select(User).where(User.username == body.username)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Username already exists")

    nickname = (body.nickname or "").strip() or body.username
    role = body.role if body.role in ROLES else "user"
    status = body.status if body.status in ("active", "pending", "rejected") else "active"
    db.add(
        User(
            username=body.username,
            password=_hash_pw(body.password),
            password_plain=_encrypt_plain(body.password),
            nickname=nickname,
            role=role,
            status=status,
        )
    )
    db.commit()
    _audit_log("create_user", body.username, body.username, ip)
    return {"ok": True, "message": f"User '{body.username}' created"}


def update_user(db: Session, user_id: int, body: AdminUserRequest, ip: str) -> dict:
    """Modify a user (admin). All fields optional. Returns an API dict."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    if body.username and body.username != user.username:
        if len(body.username) < 2:
            raise HTTPException(400, "Username too short")
        conflict = db.execute(
            select(User).where(User.username == body.username, User.id != user_id)
        ).scalar_one_or_none()
        if conflict:
            raise HTTPException(409, "Username already exists")
        user.username = body.username

    if body.password:
        if len(body.password) < 3:
            raise HTTPException(400, "Password too short")
        user.password = _hash_pw(body.password)
        user.password_plain = _encrypt_plain(body.password)

    if body.nickname is not None and body.nickname.strip():
        user.nickname = body.nickname.strip()

    if body.role and body.role in ROLES:
        user.role = body.role

    if body.status and body.status in ("active", "pending", "rejected"):
        user.status = body.status

    db.commit()

    if body.password or (body.status and body.status != "active"):
        invalidate_user_tokens(db, user.id)
        db.commit()

    _audit_log("update_user", user.username, user.username, ip)
    return {"ok": True, "message": "User updated"}


def delete_user(db: Session, user_id: int, admin: dict, ip: str) -> dict:
    """Delete a user (cannot delete self or default admin). Returns an API dict."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if str(user.id) == str(admin["id"]):
        raise HTTPException(400, "Cannot delete your own account")
    if _is_bootstrap_admin(user):
        raise HTTPException(400, "默认账号不可删除")
    invalidate_user_tokens(db, user.id)
    uname = user.username
    db.delete(user)
    db.commit()
    _audit_log("delete_user", uname, uname, ip)
    return {"ok": True, "message": f"User '{uname}' deleted"}


def change_password(
    db: Session, user_id: int, old_password: str, new_password: str, ip: str
) -> dict:
    """Change the caller's own password and invalidate all their sessions."""
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if not _verify_pw(old_password, target.password):
        raise HTTPException(400, "当前密码不正确")
    if len(new_password) < 3:
        raise HTTPException(400, "新密码太短")
    target.password = _hash_pw(new_password)
    target.password_plain = _encrypt_plain(new_password)
    target.force_pw_change = False
    invalidate_user_tokens(db, target.id)
    db.commit()
    _audit_log("password_change", target.username, target.username, ip)
    return {"ok": True, "message": "密码已修改，请重新登录"}


def deactivate_user(db: Session, user_id: int, ip: str) -> dict:
    """Deactivate (注销) the caller's own account. Default admin is protected."""
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if _is_bootstrap_admin(target):
        raise HTTPException(400, "默认账号不可注销")
    target.status = "deactivated"
    invalidate_user_tokens(db, target.id)
    db.commit()
    _audit_log("deactivate", target.username, target.username, ip)
    return {"ok": True, "message": "账号已注销"}


def update_own_profile(
    db: Session,
    user_id: int,
    nickname: str | None = None,
    old_password: str | None = None,
    new_password: str | None = None,
    ip: str = "",
) -> dict:
    """Update the caller's own profile (nickname, optional password change).

    - ``nickname`` (non-empty) updates the display name without touching the
      session, so the user stays logged in.
    - ``new_password`` requires ``old_password`` and changes the password,
      which (like :func:`change_password`) invalidates every session and
      forces a re-login.
    Returns a dict with an optional ``password_changed`` flag so the UI can
    decide whether to bounce the user to login.
    """
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")

    changed_nick = False
    if nickname is not None and nickname.strip():
        target.nickname = nickname.strip()
        changed_nick = True

    if new_password:
        if not old_password or not _verify_pw(old_password, target.password):
            raise HTTPException(400, "当前密码不正确")
        if len(new_password) < 3:
            raise HTTPException(400, "新密码太短")
        target.password = _hash_pw(new_password)
        target.password_plain = _encrypt_plain(new_password)
        target.force_pw_change = False
        invalidate_user_tokens(db, target.id)
        db.commit()
        _audit_log("password_change", target.username, target.username, ip)
        return {
            "ok": True,
            "message": "资料已更新，密码已修改，请重新登录",
            "password_changed": True,
        }

    if changed_nick:
        db.commit()
        _audit_log("update_profile", target.username, target.username, ip)
        return {"ok": True, "message": "资料已更新"}

    return {"ok": True, "message": "无变更"}


def approve_user(db: Session, user_id: int, ip: str) -> dict:
    """Approve a pending user. Returns an API dict."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or user.status != "pending":
        raise HTTPException(404, "User not found or not pending")
    user.status = "active"
    db.commit()
    _audit_log("approve", user.username, user.username, ip)
    return {"ok": True, "message": "User approved"}


def reject_user(db: Session, user_id: int, ip: str) -> dict:
    """Reject a pending user. Returns an API dict."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")
    user.status = "rejected"
    db.commit()
    _audit_log("reject", user.username, user.username, ip)
    return {"ok": True, "message": "User rejected"}


def batch_user_action(db: Session, body: AdminBatchRequest, user: dict, ip: str) -> dict:
    """Batch approve / reject / delete. Permission gate is action-dependent."""
    if body.action not in ("approve", "reject", "delete"):
        raise HTTPException(400, "Invalid action")
    if not body.ids:
        raise HTTPException(400, "No users selected")

    perms = get_permissions_for_role(user["role"])
    needed = "user:manage" if body.action == "delete" else "user:approve"
    if needed not in perms:
        raise HTTPException(403, f"Permission '{needed}' required")

    processed, failed = [], []
    for uid in body.ids:
        target = db.execute(select(User).where(User.id == uid)).scalar_one_or_none()
        if not target:
            failed.append({"id": uid, "error": "not found"})
            continue
        if body.action == "delete":
            if str(target.id) == str(user["id"]):
                failed.append({"id": uid, "error": "cannot delete self"})
                continue
            if _is_bootstrap_admin(target):
                failed.append({"id": uid, "error": "default account protected"})
                continue
            invalidate_user_tokens(db, target.id)
            db.delete(target)
        elif body.action == "approve":
            target.status = "active"
        else:  # reject
            target.status = "rejected"
        processed.append(uid)

    db.commit()
    _audit_log(
        "batch_" + body.action, f"{len(processed)} user(s)", user["username"], ip
    )
    return {"ok": True, "action": body.action, "processed": processed, "failed": failed}
