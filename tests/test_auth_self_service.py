# -*- coding: utf-8 -*-
"""Self-service auth tests: profile update, password change, session
invalidation, refresh-token rotation, and account deactivation.

These lock in the ARCH-9 session semantics:

  * a nickname-only ``PUT /api/auth/me`` keeps the session alive;
  * a password change (via ``PUT /api/auth/me`` *or* ``PUT /api/auth/me/password``)
    invalidates EVERY refresh token for that user, forcing re-login;
  * ``POST /api/auth/refresh`` rotates the refresh token — the presented token
    is single-use and is revoked after a successful refresh;
  * a deactivated account's *old* access token stays valid until its TTL
    lapses (ARCH-9: stateless JWTs can't be revoked early), but a *fresh*
    login is refused (403).
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


def _user_id(admin_token: str, username: str) -> int:
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    for u in resp.json()["users"]:
        if u["username"] == username:
            return u["id"]
    raise AssertionError(f"user {username} not found")


def _make_active_user(username: str, password: str = "testpass", role: str = "user") -> int:
    admin = _admin_token()
    r = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        json={"username": username, "password": password, "role": role, "status": "active"},
    )
    assert r.status_code == 200, r.text
    return _user_id(admin, username)


class TestProfileUpdate:
    def test_nickname_only_no_password_flag(self):
        uname = _unique("prof")
        uid = _make_active_user(uname, "prof1234")
        token = client.post("/api/auth/login", json={"username": uname, "password": "prof1234"}).json()["token"]
        r = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"nickname": "NewNick"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        assert r.json().get("password_changed") is not True
        # Session still valid + nickname persisted.
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json().get("nickname") == "NewNick"
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_profile_bad_old_password_rejected(self):
        uname = _unique("prof")
        uid = _make_active_user(uname, "prof1234")
        token = client.post("/api/auth/login", json={"username": uname, "password": "prof1234"}).json()["token"]
        r = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "wrong", "new_password": "new5678"},
        )
        assert r.status_code == 400, r.text
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})


class TestPasswordChange:
    def test_change_password_wrong_old_rejected(self):
        uname = _unique("pw")
        uid = _make_active_user(uname, "oldpass1")
        token = client.post("/api/auth/login", json={"username": uname, "password": "oldpass1"}).json()["token"]
        r = client.put(
            "/api/auth/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "nope", "new_password": "newpass1"},
        )
        assert r.status_code == 400, r.text
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_change_password_invalidates_all_sessions(self):
        uname = _unique("pw")
        uid = _make_active_user(uname, "oldpass1")
        login = client.post("/api/auth/login", json={"username": uname, "password": "oldpass1"}).json()
        access = login["token"]
        refresh = login["refresh_token"]

        # Change password (correct old password).
        r = client.put(
            "/api/auth/me/password",
            headers={"Authorization": f"Bearer {access}"},
            json={"old_password": "oldpass1", "new_password": "newpass1"},
        )
        assert r.status_code == 200, r.text

        # The previous refresh token is now dead (all sessions revoked).
        rr = client.post("/api/auth/refresh", json={"refresh_token": refresh})
        assert rr.status_code == 401, rr.text

        # New password works.
        login2 = client.post("/api/auth/login", json={"username": uname, "password": "newpass1"})
        assert login2.status_code == 200

        # Clean up the now-recreated account.
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_me_password_change_invalidates_sessions(self):
        uname = _unique("pw")
        uid = _make_active_user(uname, "oldpass1")
        login = client.post("/api/auth/login", json={"username": uname, "password": "oldpass1"}).json()
        access = login["token"]
        refresh = login["refresh_token"]

        r = client.put(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access}"},
            json={"old_password": "oldpass1", "new_password": "newpass1"},
        )
        assert r.status_code == 200 and r.json().get("password_changed") is True

        # Old refresh token revoked.
        rr = client.post("/api/auth/refresh", json={"refresh_token": refresh})
        assert rr.status_code == 401
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})


class TestRefreshRotation:
    def test_refresh_rotates_and_revokes_old(self):
        uname = _unique("rot")
        uid = _make_active_user(uname, "rotpass1")
        login = client.post("/api/auth/login", json={"username": uname, "password": "rotpass1"}).json()
        old_refresh = login["refresh_token"]

        r2 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 200, r2.text
        new = r2.json()
        assert new["refresh_token"] != old_refresh
        assert new["access_token"]

        # The rotated-out token can no longer be used.
        r3 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r3.status_code == 401, r3.text
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_invalid_refresh_rejected(self):
        r = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert r.status_code == 401

    def test_refresh_keeps_access_working(self):
        uname = _unique("rot")
        uid = _make_active_user(uname, "rotpass1")
        login = client.post("/api/auth/login", json={"username": uname, "password": "rotpass1"}).json()
        r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
        assert r.status_code == 200
        new_access = r.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})


class TestDeactivate:
    def test_deactivated_user_cannot_relogin(self):
        uname = _unique("deact")
        uid = _make_active_user(uname, "deact123")
        token = client.post("/api/auth/login", json={"username": uname, "password": "deact123"}).json()["token"]
        r = client.post("/api/auth/me/deactivate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json().get("ok")
        # ARCH-9 trade-off: the stateless access JWT remains valid until its TTL
        # lapses, so the *old* token still authenticates (it cannot be revoked
        # early)...
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        # ...but a *fresh* login is refused because the account is deactivated.
        relogin = client.post("/api/auth/login", json={"username": uname, "password": "deact123"})
        assert relogin.status_code == 403
        # Admin can still remove the deactivated account.
        admin = _admin_token()
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})
