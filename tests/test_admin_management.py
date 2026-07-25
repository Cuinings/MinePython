# -*- coding: utf-8 -*-
"""Admin management endpoint tests (RBAC-gated).

Covers the user-CRUD / approval surface that had no automated coverage:

  * ``PUT  /api/admin/users/{id}`` — role change / password change
    (invalidates the user's sessions) / 404 for unknown id;
  * ``DELETE /api/admin/users/{id}`` — cannot delete self, cannot delete the
    default admin, can delete a normal user;
  * ``POST /api/admin/users/batch`` — approve / reject / delete in bulk;
  * ``PUT  /api/admin/users/{id}/reject`` — pending -> rejected (cannot login);
  * ``GET/PUT /api/admin/site`` and ``GET/PUT /api/admin/upload-limit``.

The site / upload-limit setters persist to ``.env``; those calls are
neutralized with a no-op ``_write_env_key`` so the test never touches the real
project ``.env``, and the in-memory values are restored afterwards.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import modules.user.config as _cfg
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


def _create_user(username: str, password: str = "testpass", role: str = "user", status: str = "active") -> int:
    admin = _admin_token()
    r = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {admin}"},
        json={"username": username, "password": password, "role": role, "status": status},
    )
    assert r.status_code == 200, r.text
    return _user_id(admin, username)


def _user_id(admin_token: str, username: str) -> int:
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    for u in resp.json()["users"]:
        if u["username"] == username:
            return u["id"]
    raise AssertionError(f"user {username} not found")


class TestUpdateUser:
    def test_update_role(self):
        uname = _unique("upd")
        uid = _create_user(uname)
        admin = _admin_token()
        r = client.put(
            f"/api/admin/users/{uid}",
            headers={"Authorization": f"Bearer {admin}"},
            json={"role": "reviewer"},
        )
        assert r.status_code == 200, r.text
        # Confirm the role took effect via the user list.
        listing = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin}"}).json()
        u = next(x for x in listing["users"] if x["username"] == uname)
        assert u["role"] == "reviewer"
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_update_password_invalidates_sessions(self):
        uname = _unique("upd")
        uid = _create_user(uname, "oldpass1")
        login = client.post("/api/auth/login", json={"username": uname, "password": "oldpass1"}).json()
        refresh = login["refresh_token"]

        admin = _admin_token()
        r = client.put(
            f"/api/admin/users/{uid}",
            headers={"Authorization": f"Bearer {admin}"},
            json={"password": "brandnew1"},
        )
        assert r.status_code == 200, r.text

        # The old session's refresh token is revoked.
        rr = client.post("/api/auth/refresh", json={"refresh_token": refresh})
        assert rr.status_code == 401
        # New password works.
        assert client.post("/api/auth/login", json={"username": uname, "password": "brandnew1"}).status_code == 200
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_update_unknown_id_404(self):
        admin = _admin_token()
        r = client.put(
            f"/api/admin/users/999999",
            headers={"Authorization": f"Bearer {admin}"},
            json={"nickname": "x"},
        )
        assert r.status_code == 404


class TestDeleteUser:
    def test_cannot_delete_self(self):
        admin = _admin_token()
        uid = _user_id(admin, "admin")
        r = client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 400
        assert "delete" in r.json().get("detail", "").lower()

    def test_cannot_delete_default_admin(self):
        admin = _admin_token()
        uid = _user_id(admin, "admin")
        r = client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 400
        assert "delete" in r.json().get("detail", "").lower()

    def test_delete_normal_user(self):
        uname = _unique("del")
        uid = _create_user(uname)
        admin = _admin_token()
        r = client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 200, r.text
        # Gone from the list.
        listing = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin}"}).json()
        assert all(u["username"] != uname for u in listing["users"])


class TestBatchUserActions:
    def test_batch_approve(self):
        admin = _admin_token()
        uname = _unique("bapp")
        client.post("/api/auth/register", json={"username": uname, "password": "testpass", "nickname": uname})
        uid = _user_id(admin, uname)
        r = client.post(
            "/api/admin/users/batch",
            headers={"Authorization": f"Bearer {admin}"},
            json={"ids": [uid], "action": "approve"},
        )
        assert r.status_code == 200, r.text
        assert uid in r.json()["processed"]
        # Now active -> can login.
        assert client.post("/api/auth/login", json={"username": uname, "password": "testpass"}).status_code == 200
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_batch_reject(self):
        admin = _admin_token()
        uname = _unique("brej")
        client.post("/api/auth/register", json={"username": uname, "password": "testpass", "nickname": uname})
        uid = _user_id(admin, uname)
        r = client.post(
            "/api/admin/users/batch",
            headers={"Authorization": f"Bearer {admin}"},
            json={"ids": [uid], "action": "reject"},
        )
        assert r.status_code == 200, r.text
        assert uid in r.json()["processed"]
        # Rejected -> cannot login.
        assert client.post("/api/auth/login", json={"username": uname, "password": "testpass"}).status_code == 403
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})

    def test_batch_delete(self):
        admin = _admin_token()
        uname = _unique("bdel")
        uid = _create_user(uname)
        r = client.post(
            "/api/admin/users/batch",
            headers={"Authorization": f"Bearer {admin}"},
            json={"ids": [uid], "action": "delete"},
        )
        assert r.status_code == 200, r.text
        assert uid in r.json()["processed"]
        listing = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin}"}).json()
        assert all(u["username"] != uname for u in listing["users"])

    def test_batch_invalid_action_400(self):
        admin = _admin_token()
        r = client.post(
            "/api/admin/users/batch",
            headers={"Authorization": f"Bearer {admin}"},
            json={"ids": [], "action": "explode"},
        )
        assert r.status_code == 400


class TestRejectEndpoint:
    def test_reject_makes_login_fail(self):
        admin = _admin_token()
        uname = _unique("rej")
        client.post("/api/auth/register", json={"username": uname, "password": "testpass", "nickname": uname})
        uid = _user_id(admin, uname)
        r = client.put(f"/api/admin/users/{uid}/reject", headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 200, r.text
        assert client.post("/api/auth/login", json={"username": uname, "password": "testpass"}).status_code == 403
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})


class TestSiteAndUploadLimit:
    def test_site_get_and_set(self, monkeypatch):
        orig = _cfg.APP_NAME
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        admin = _admin_token()
        g = client.get("/api/admin/site", headers={"Authorization": f"Bearer {admin}"})
        assert g.status_code == 200 and "name" in g.json()
        r = client.put(
            "/api/admin/site",
            headers={"Authorization": f"Bearer {admin}"},
            json={"name": "RenamedSite"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "RenamedSite"
        # Restore in-memory branding so other suites are unaffected.
        _cfg.APP_NAME = orig

    def test_upload_limit_get_and_set(self, monkeypatch):
        orig_mb = _cfg.MAX_UPLOAD_SIZE_MB
        orig_bytes = _cfg.MAX_UPLOAD_SIZE_BYTES
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        admin = _admin_token()
        g = client.get("/api/admin/upload-limit", headers={"Authorization": f"Bearer {admin}"})
        assert g.status_code == 200 and "max_upload_size_mb" in g.json()
        r = client.put(
            "/api/admin/upload-limit",
            headers={"Authorization": f"Bearer {admin}"},
            json={"max_upload_size_mb": 1234},
        )
        assert r.status_code == 200, r.text
        assert r.json()["max_upload_size_mb"] == 1234
        # Restore in-memory limits.
        _cfg.MAX_UPLOAD_SIZE_MB = orig_mb
        _cfg.MAX_UPLOAD_SIZE_BYTES = orig_bytes

    def test_site_empty_name_rejected(self, monkeypatch):
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        admin = _admin_token()
        r = client.put(
            "/api/admin/site",
            headers={"Authorization": f"Bearer {admin}"},
            json={"name": "   "},
        )
        assert r.status_code == 400
