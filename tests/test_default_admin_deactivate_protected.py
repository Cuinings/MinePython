# -*- coding: utf-8 -*-
"""Regression test: the default built-in admin account must NOT be deletable /
deactivatable, while every other account remains free to deactivate itself.

This is the pytest-native replacement for the former live-server script. It
runs hermetically against an in-process :class:`fastapi.testclient.TestClient`
(backend enforcement = defence-in-depth behind the UI hiding done in
``files.html`` / ``users.html``).

Verified:

  * the seeded default admin (``is_default = True``) is flagged as such;
  * it CANNOT deactivate itself via ``POST /api/auth/me/deactivate``
    (HTTP 400, "默认账号不可注销") and stays active afterwards;
  * a normal (non-default) user CAN deactivate their own account (HTTP 200)
    — proving the protection is scoped to the default admin only.
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


class TestDefaultAdminDeactivateProtected:
    def test_default_admin_is_flagged(self):
        token = _admin_token()
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json().get("is_default") is True

    def test_default_admin_cannot_deactivate(self):
        token = _admin_token()
        r = client.post("/api/auth/me/deactivate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "默认" in detail or "注销" in detail
        # The default admin must remain active after the rejected attempt.
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json().get("status") == "active"

    def test_normal_user_can_deactivate(self):
        uname = _unique("dap")
        admin = _admin_token()
        r = client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin}"},
            json={"username": uname, "password": "dap12345", "role": "user", "status": "active"},
        )
        assert r.status_code == 200, r.text
        uid = r.json().get("id") or next(
            u["id"] for u in client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin}"}).json()["users"]
            if u["username"] == uname
        )
        token = client.post("/api/auth/login", json={"username": uname, "password": "dap12345"}).json()["token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json().get("is_default") is not True

        r = client.post("/api/auth/me/deactivate", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json().get("ok")

        # Clean up the (now deactivated) test user.
        client.delete(f"/api/admin/users/{uid}", headers={"Authorization": f"Bearer {admin}"})
