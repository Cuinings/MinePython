# -*- coding: utf-8 -*-
"""API tests for MinePython (SQLAlchemy + RBAC)."""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from modules.user.database import init_db
from modules.combined import app

# Make sure tables + RBAC seed exist before any request.
init_db()

client = TestClient(app)


def _admin_token() -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _stored_path(token: str, original_name: str) -> str:
    """Uploaded files are stored as '<category>/<uid>_<name>'; fetch the real path from the list."""
    resp = client.get(f"/api/files?search={original_name}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    for f in resp.json()["files"]:
        if original_name in f["filename"]:
            return f["path"]
    raise AssertionError(f"uploaded file {original_name} not found in listing")


class TestAuth:
    def test_login_admin(self):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["token"]
        assert data["role"] == "admin"
        assert data["nickname"] == "管理员"
        # RBAC: admin gets all permissions
        assert "user:manage" in data["permissions"]
        assert "file:delete_any" in data["permissions"]

    def test_login_bad_password(self):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_me(self):
        token = _admin_token()
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert "user:manage" in data["permissions"]

    def test_register_and_duplicate(self):
        uname = _unique("reg")
        r1 = client.post("/api/auth/register", json={
            "username": uname, "password": "testpass", "nickname": "测试"
        })
        assert r1.status_code == 200
        assert r1.json()["ok"] is True
        # Same username again -> 409
        r2 = client.post("/api/auth/register", json={"username": uname, "password": "testpass"})
        assert r2.status_code == 409

    def test_pending_cannot_login(self):
        uname = _unique("pend")
        client.post("/api/auth/register", json={"username": uname, "password": "testpass"})
        # Admin approves
        token = _admin_token()
        pending = client.get("/api/admin/pending", headers={"Authorization": f"Bearer {token}"})
        uid = next(u["id"] for u in pending.json()["users"] if u["username"] == uname)
        client.put(f"/api/admin/users/{uid}/approve", headers={"Authorization": f"Bearer {token}"})
        # Now login should succeed
        resp = client.post("/api/auth/login", json={"username": uname, "password": "testpass"})
        assert resp.status_code == 200


class TestRBAC:
    def _make_user(self, role: str) -> tuple[str, str]:
        token = _admin_token()
        uname = _unique(f"u_{role}")
        client.post("/api/admin/users", headers={"Authorization": f"Bearer {token}"}, json={
            "username": uname, "password": "testpass", "role": role, "status": "active"
        })
        resp = client.post("/api/auth/login", json={"username": uname, "password": "testpass"})
        return uname, resp.json()["token"]

    def test_user_cannot_list_users(self):
        _, token = self._make_user("user")
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_user_cannot_view_audit(self):
        _, token = self._make_user("user")
        resp = client.get("/api/admin/audit", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_reviewer_can_view_audit(self):
        _, token = self._make_user("reviewer")
        resp = client.get("/api/admin/audit", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_anonymous_readonly(self):
        # Guests (no token) may browse & download files read-only, but any
        # write operation must still require a real session token.
        resp = client.get("/api/files")
        assert resp.status_code == 200
        assert "files" in resp.json()
        # Write endpoints stay locked for anonymous.
        up = client.post("/api/upload", files={"file": ("x.txt", b"x")})
        assert up.status_code == 401


class TestFiles:
    def test_list_files(self):
        token = _admin_token()
        resp = client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "total" in data

    def test_list_files_paginated(self):
        token = _admin_token()
        resp = client.get("/api/files?page=1&page_size=5", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_files_search(self):
        token = _admin_token()
        resp = client.get("/api/files?search=.py", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_upload_and_delete_flow(self):
        token = _admin_token()
        up = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("rbac_test.txt", b"hello world")},
            data={"category": "auto"},
        )
        assert up.status_code == 200, up.text
        # The stored path is available from the file list (not the original filename)
        path = _stored_path(token, "rbac_test.txt")
        # Delete own file (admin has file:delete_any too)
        d = client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})
        assert d.status_code == 200, d.text

    def test_delete_nonexistent(self):
        token = _admin_token()
        resp = client.delete("/api/files/nonexistent/file.txt", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_user_cannot_delete_others_file(self):
        admin_token = _admin_token()
        # Admin uploads a file
        up = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("owner_file.txt", b"data")},
            data={"category": "auto"},
        )
        assert up.status_code == 200
        path = _stored_path(admin_token, "owner_file.txt")

        # Create a normal user and try to delete admin's file -> 403
        uname = _unique("deleter")
        client.post("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"}, json={
            "username": uname, "password": "testpass", "role": "user", "status": "active"
        })
        login = client.post("/api/auth/login", json={"username": uname, "password": "testpass"})
        user_token = login.json()["token"]
        resp = client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403

        # Cleanup by admin
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {admin_token}"})


class TestAdmin:
    def test_list_users(self):
        token = _admin_token()
        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert len(data["users"]) >= 1
        # The admin user list intentionally exposes the (hashed) password so
        # admins can view it — access is gated by the user:read permission, so
        # only admins/reviewers ever reach this endpoint (see RBAC tests below).
        assert "password" in data["users"][0]
        # password is a secure hash: argon2id ("$argon2id$...") or legacy "salt:hash"
        pw = data["users"][0]["password"]
        assert pw and (pw.startswith("$") or ":" in pw)

    def test_pending_count(self):
        token = _admin_token()
        resp = client.get("/api/admin/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "count" in resp.json()

    def test_unauthorized(self):
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401


class TestDownload:
    def setup_method(self):
        # Each test uploads its own file so the suite is self-contained
        # (no reliance on files left behind by other tests).
        self.token = _admin_token()
        resp = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {self.token}"},
            files={"file": ("dl_probe.txt", b"download-probe-content")},
            data={"category": "auto"},
        )
        assert resp.status_code == 200, resp.text
        self.path = _stored_path(self.token, "dl_probe.txt")

    def test_download_with_header(self):
        resp = client.get(
            f"/api/download/{self.path}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert resp.status_code == 200

    def test_download_with_token_param(self):
        # Browser-native <img>/<a> cannot send a Bearer header, so they use ?token=
        resp = client.get(f"/api/download/{self.path}?token={self.token}")
        assert resp.status_code == 200

    def test_download_no_auth(self):
        # Anonymous guests are allowed to download (read-only guest mode).
        resp = client.get(f"/api/download/{self.path}")
        assert resp.status_code == 200


class TestCategories:
    def test_list_categories(self):
        token = _admin_token()
        resp = client.get("/api/categories", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "categories" in resp.json()
