# -*- coding: utf-8 -*-
"""UCenter end-to-end smoke test (pytest, hermetic via TestClient).

This is the pytest-native replacement for the former live-server smoke
script. It runs against an in-process :class:`fastapi.testclient.TestClient`
so it is collected and executed by ``pytest`` / CI and never aborts
collection (the old script asserted at import time against a live
``http://127.0.0.1:8000`` server).

It exercises the full self-service account lifecycle:

  * admin ``GET /api/auth/me`` shape (permissions + role)
  * ``PUT /api/auth/me`` nickname-only keeps the session
    (no ``password_changed`` flag)
  * ``PUT /api/auth/me`` with a password change flags ``password_changed``
    and forces a re-login
  * register -> approve -> login a normal user
  * normal user ``GET /api/auth/me`` + ``PUT`` profile
  * normal user CANNOT open the admin user list (403)
  * normal user can deactivate their own account (token then 401)
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from modules.user.database import init_db
from modules.combined import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _register_approve_login(username: str, password: str = "uctestpw") -> tuple[int, str]:
    """Register (pending) + admin-approve + login a normal user."""
    admin = _admin_token()
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": username},
    )
    assert r.status_code == 200, r.text
    pending = client.get("/api/admin/pending", headers={"Authorization": f"Bearer {admin}"})
    uid = next(u["id"] for u in pending.json()["users"] if u["username"] == username)
    client.put(f"/api/admin/users/{uid}/approve", headers={"Authorization": f"Bearer {admin}"})
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return uid, login.json()["token"]


class TestUCenterSmoke:
    def test_admin_me_shape(self):
        token = _admin_token()
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "admin"
        assert d["permissions"]
        assert "user:manage" in d["permissions"]
        assert "file:delete_any" in d["permissions"]

    def test_nickname_only_update_keeps_session(self):
        token = _admin_token()
        r = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"nickname": "AdminRenamed"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Nickname-only update must NOT flag a password change.
        assert r.json().get("password_changed") is not True
        # The session is untouched; the new nickname is persisted.
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json().get("nickname") == "AdminRenamed"
        # Restore the seeded default nickname so other suites are unaffected.
        client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"nickname": "管理员"},
        )

    def test_password_change_forces_relogin(self):
        token = _admin_token()
        # Change password (same value) -> flagged, forces re-login.
        r = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"nickname": "管理员", "old_password": "admin123", "new_password": "admin123"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("password_changed") is True
        # Re-login so subsequent admin calls in this session stay valid.
        assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200

    def test_register_approve_login_normal_user(self):
        uname = _unique("uctest")
        uid, token = _register_approve_login(uname)
        assert uid
        assert token
        # Normal user sees only their own permissions (no admin grants).
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        perms = me.json()["permissions"]
        assert "user:manage" not in perms
        # Cleanup.
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_normal_user_profile_and_403(self):
        uname = _unique("uctest")
        uid, token = _register_approve_login(uname)
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        prof = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"nickname": "UC Renamed"},
        )
        assert prof.status_code == 200 and prof.json().get("ok")
        # A normal user is blocked from the admin user list.
        admin_list = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert admin_list.status_code == 403
        # Cleanup.
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_normal_user_deactivate(self):
        uname = _unique("ucdeact")
        _admin = _admin_token()
        r = client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {_admin}"},
            json={"username": uname, "password": "uctestpw", "role": "user", "status": "active"},
        )
        assert r.status_code == 200, r.text
        token = client.post("/api/auth/login", json={"username": uname, "password": "uctestpw"}).json()["token"]
        r = client.post("/api/auth/me/deactivate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json().get("ok")
        # ARCH-9: the stateless access JWT stays valid until its TTL lapses, so
        # the *old* token still authenticates; a *fresh* login is refused (403).
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        relogin = client.post("/api/auth/login", json={"username": uname, "password": "uctestpw"})
        assert relogin.status_code == 403
