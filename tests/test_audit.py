# -*- coding: utf-8 -*-
"""Tests for the public, permission-scoped audit-log endpoint (/api/audit/logs).

Rules verified:
  * Anonymous (no token) is rejected with 401.
  * A regular user (role=user) can read the endpoint but is server-scoped to
    their OWN records only (scope == "self"), never another user's.
  * An admin (role=admin, holding audit:view) sees ALL records
    (scope == "all", can_view_all == True).
  * Even if a regular user smuggles a `user=` filter, the server ignores it
    and still returns only their own rows (defence in depth).
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from modules.user.database import init_db
from modules.combined import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _make_active_user(role: str) -> tuple[str, str]:
    """Create + activate a user of the given role; return (username, token)."""
    admin = _admin_token()
    uname = _unique(f"aud_{role}")
    r = client.post("/api/admin/users", headers={"Authorization": f"Bearer {admin}"}, json={
        "username": uname, "password": "testpass", "role": role, "status": "active"
    })
    assert r.status_code == 200, r.text
    login = client.post("/api/auth/login", json={"username": uname, "password": "testpass"})
    assert login.status_code == 200, login.text
    return uname, login.json()["token"]


def _seed_audit_for(username: str, token: str, action: str = "login") -> None:
    """Create an auditable action attributed to username (uses its token)."""
    client.post(
        "/api/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (f"{username}_{action}.txt", b"x")},
        data={"category": "auto"},
    )


class TestAuditLogsPublic:
    def test_anonymous_rejected(self):
        resp = client.get("/api/audit/logs")
        assert resp.status_code == 401

    def test_user_self_scope(self):
        uname, token = _make_active_user("user")
        _seed_audit_for(uname, token)  # creates an "upload" audit row for this user

        resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scope"] == "self"
        assert data["can_view_all"] is False
        # Every returned row belongs to this user.
        assert data["logs"]
        for row in data["logs"]:
            assert row["username"] == uname

    def test_user_cannot_see_others(self):
        # Two distinct users, each with their own audit rows.
        a_name, a_token = _make_active_user("user")
        b_name, b_token = _make_active_user("user")
        _seed_audit_for(a_name, a_token)
        _seed_audit_for(b_name, b_token)

        resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {a_token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Even though user A tries to filter by user B, the server ignores it.
        resp2 = client.get(
            f"/api/audit/logs?user_filter={b_name}",
            headers={"Authorization": f"Bearer {a_token}"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["scope"] == "self"
        for row in data2["logs"]:
            assert row["username"] == a_name  # never B's rows

    def test_admin_sees_all(self):
        admin_token = _admin_token()
        a_name, a_token = _make_active_user("user")
        _seed_audit_for(a_name, a_token)
        _seed_audit_for("admin", admin_token)

        resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scope"] == "all"
        assert data["can_view_all"] is True
        # Admin's view includes the other user's rows.
        usernames = {row["username"] for row in data["logs"]}
        assert a_name in usernames
        assert "admin" in usernames

    def test_reviewer_sees_all(self):
        r_name, r_token = _make_active_user("reviewer")
        a_name, a_token = _make_active_user("user")
        _seed_audit_for(a_name, a_token)

        resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {r_token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["scope"] == "all"
        assert a_name in {row["username"] for row in data["logs"]}

    def test_admin_user_filter(self):
        admin_token = _admin_token()
        a_name, a_token = _make_active_user("user")
        _seed_audit_for(a_name, a_token)

        resp = client.get(
            f"/api/audit/logs?user_filter={a_name}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "all"
        assert data["logs"]
        for row in data["logs"]:
            assert row["username"] == a_name

    def test_download_is_audited(self):
        # A successful download must produce a `download` audit row attributed
        # to the downloading user (closes the previously-untracked gap).
        uname, token = _make_active_user("user")
        client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"{uname}_dl.txt", b"x")},
            data={"category": "auto"},
        )
        files = client.get(
            "/api/files", headers={"Authorization": f"Bearer {token}"}
        ).json().get("files", [])
        assert files, "upload did not persist a file"
        fp = files[-1]["filepath"]
        # Download with the access token, exactly like the UI's downloadUrl().
        dl = client.get(f"/api/download/{fp}?token={token}")
        assert dl.status_code == 200, dl.text
        # The download must now appear in this user's own audit log.
        resp = client.get(
            "/api/audit/logs?action=download",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        rows = resp.json()["logs"]
        assert any(r["action"] == "download" and r["username"] == uname for r in rows), rows


class TestAuditClear:
    """Destructive clear endpoint (POST /api/admin/audit/clear)."""

    def test_reviewer_cannot_clear(self):
        # Clearing is admin-only (audit:purge); reviewers must be 403'd.
        r_token = _make_active_user("reviewer")[1]
        resp = client.post(
            "/api/admin/audit/clear",
            headers={"Authorization": f"Bearer {r_token}"},
            json={"confirm": True},
        )
        assert resp.status_code == 403, resp.text

    def test_clear_requires_confirm(self):
        admin_token = _admin_token()
        resp = client.post(
            "/api/admin/audit/clear",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirm": False},
        )
        assert resp.status_code == 400, resp.text

    def test_admin_can_clear_and_leaves_trail(self):
        admin_token = _admin_token()
        # Seed a couple of records first.
        u_name, u_token = _make_active_user("user")
        _seed_audit_for(u_name, u_token)
        _seed_audit_for(u_name, u_token, "logout")
        before = client.get(
            "/api/audit/logs", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()["total"]
        assert before >= 2

        resp = client.post(
            "/api/admin/audit/clear",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirm": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["cleared"] >= 2
        assert data["cleared_by"] == "admin"

        # After clearing, exactly ONE record survives: the audit_clear trail.
        after = client.get(
            "/api/audit/logs", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert after["total"] == 1
        assert after["logs"][0]["action"] == "audit_clear"
        assert after["logs"][0]["username"] == "admin"
