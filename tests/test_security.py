# -*- coding: utf-8 -*-
"""Security / edge-case tests (P1-8): login lockout & IP throttle, multi-session
token isolation, token expiry + cleanup, batch-download caps, response schemas.
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import modules.user.auth as auth
from modules.user.auth import authenticate_token, purge_expired_tokens
from modules.user.database import SessionLocal, SessionToken, User, init_db
from modules.combined import app
from sqlalchemy import select

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _make_active_user(password: str = "testpass", role: str = "user") -> str:
    """Create an active user via the admin API; return its username."""
    token = _admin_token()
    uname = _unique("sec")
    r = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": uname, "password": password, "role": role, "status": "active"},
    )
    assert r.status_code == 200, r.text
    return uname


# ---------------------------------------------------------------------------
# ARCH-2 — login rate limiting
# ---------------------------------------------------------------------------
class TestLoginLockout:
    def test_account_locks_after_threshold(self):
        from modules.user.config import MAX_LOGIN_FAILS

        uname = _make_active_user(password="rightpass")
        auth._clear_login_failures(uname)
        # First MAX_LOGIN_FAILS wrong attempts return 401 (not yet locked)...
        for _ in range(MAX_LOGIN_FAILS):
            r = client.post("/api/auth/login", json={"username": uname, "password": "nope"})
            assert r.status_code == 401, r.text
        # ...the next attempt trips the lock -> 429.
        r = client.post("/api/auth/login", json={"username": uname, "password": "nope"})
        assert r.status_code == 429, r.text
        # Even the CORRECT password is refused while locked.
        r = client.post("/api/auth/login", json={"username": uname, "password": "rightpass"})
        assert r.status_code == 429, r.text
        auth._clear_login_failures(uname)

    def test_ip_throttle_helpers(self, monkeypatch):
        """The IP-dimension throttle logic (exercised directly, deterministic).

        The threshold lives in :mod:`modules.user.config` (centralized via ARCH-8); the
        service reads it at call time, so we patch the config module, not the
        re-exported names on :mod:`modules.user.auth`.
        """
        import modules.user.config as _cfg

        ip = "203.0.113.7"
        auth._clear_ip_failures(ip)
        monkeypatch.setattr(_cfg, "LOGIN_IP_MAX_FAILS", 3)
        try:
            assert auth._ip_throttled(ip) == 0
            for _ in range(4):  # cap (3) + 1 to exceed
                auth._register_ip_failure(ip)
            # Once failures exceed the cap the IP is throttled for the window.
            assert auth._ip_throttled(ip) > 0
            # A successful login clears the IP's counter.
            auth._clear_ip_failures(ip)
            assert auth._ip_throttled(ip) == 0
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# Multi-session token isolation
# ---------------------------------------------------------------------------
class TestMultiSession:
    def test_independent_sessions(self):
        uname = _make_active_user(password="multipass")
        t1 = client.post("/api/auth/login", json={"username": uname, "password": "multipass"}).json()["token"]
        t2 = client.post("/api/auth/login", json={"username": uname, "password": "multipass"}).json()["token"]
        assert t1 and t2 and t1 != t2
        # Both sessions are valid.
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"}).status_code == 200
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200
        # Logging out one session does NOT invalidate the other.
        assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {t1}"}).status_code == 200
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"}).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200


# ---------------------------------------------------------------------------
# ARCH-3 — token expiry + cleanup
# ---------------------------------------------------------------------------
class TestTokenExpiry:
    def _admin_id(self) -> int:
        with SessionLocal() as db:
            return db.execute(select(User).where(User.username == "admin")).scalar_one().id

    def test_expired_token_rejected_and_purged(self):
        admin_id = self._admin_id()
        dead = "expired_" + uuid.uuid4().hex
        with SessionLocal() as db:
            db.add(SessionToken(user_id=admin_id, token=dead,
                                expires_at="2000-01-01 00:00:00", device="test"))
            db.commit()
        # An expired token authenticates as nobody.
        assert authenticate_token(dead) is None
        # The cleanup sweep physically removes it.
        removed = purge_expired_tokens()
        assert removed >= 1
        with SessionLocal() as db:
            assert db.execute(select(SessionToken).where(SessionToken.token == dead)).scalar_one_or_none() is None

    def test_fresh_token_survives_purge(self):
        token = _admin_token()
        purge_expired_tokens()
        # A freshly minted (non-expired) token is untouched by the sweep.
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


# ---------------------------------------------------------------------------
# P1-5 — batch download caps
# ---------------------------------------------------------------------------
class TestBatchDownloadCaps:
    def test_too_many_files_rejected(self):
        from modules.user.config import MAX_BATCH_DOWNLOAD_FILES
        token = _admin_token()
        paths = [f"其他/ghost_{i}.txt" for i in range(MAX_BATCH_DOWNLOAD_FILES + 1)]
        r = client.post("/api/files/batch-download",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"paths": paths})
        assert r.status_code == 400, r.text
        assert "limit" in r.text.lower()

    def test_empty_selection_rejected(self):
        token = _admin_token()
        r = client.post("/api/files/batch-download",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"paths": []})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# ARCH-5 — response schema shape
# ---------------------------------------------------------------------------
class TestResponseSchemas:
    def test_file_list_schema(self):
        token = _admin_token()
        # Seed one file so an item is present to shape-check.
        client.post("/api/upload", headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("schema_probe.txt", b"x")}, data={"category": "auto"})
        r = client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("files", "total", "page", "page_size"):
            assert k in data
        if data["files"]:
            item = data["files"][0]
            # Declared + computed (extra="allow") fields must all survive.
            for k in ("id", "filename", "path", "size_human", "uploader_nickname"):
                assert k in item, f"missing {k} in file item"

    def test_user_list_schema(self):
        token = _admin_token()
        r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        u = r.json()["users"][0]
        # The admin-only plaintext/hashed password extras must not be dropped.
        for k in ("id", "username", "role", "status", "password"):
            assert k in u

    def test_audit_list_schema(self):
        token = _admin_token()
        r = client.get("/api/admin/audit", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "logs" in r.json()


# ---------------------------------------------------------------------------
# ARCH-1 — error response convergence (no internal leak in production)
# ---------------------------------------------------------------------------
import asyncio
import json as _json

import modules.user.config as app_config
from fastapi import Request as _Request
from modules.common import global_exception_handler as _global_exc_handler


def _fake_request() -> _Request:
    return _Request({
        "type": "http", "method": "GET", "path": "/boom", "raw_path": b"/boom",
        "query_string": b"", "headers": [], "scheme": "http", "server": ("testserver", 80),
    })


class TestErrorConvergence:
    def test_handler_hides_error_when_debug_off(self):
        """Production default: no `error` field, only a generic detail."""
        resp = asyncio.run(_global_exc_handler(_fake_request(), RuntimeError("SECRET_TRACEBACK")))
        body = _json.loads(resp.body)
        assert resp.status_code == 500
        assert "error" not in body
        assert body["detail"] == "Internal server error"

    def test_handler_leaks_error_when_debug_on(self, monkeypatch):
        monkeypatch.setattr(app_config, "DEBUG", True)
        resp = asyncio.run(_global_exc_handler(_fake_request(), RuntimeError("SECRET_TRACEBACK")))
        body = _json.loads(resp.body)
        assert body.get("error") == "SECRET_TRACEBACK"


# ---------------------------------------------------------------------------
# R3 — interactive API docs gated behind DEBUG
# ---------------------------------------------------------------------------
class TestDocsGating:
    def test_docs_blocked_in_prod(self):
        """Default test env (APP_DEBUG unset -> False) must block docs."""
        assert client.get("/docs").status_code == 403
        assert client.get("/redoc").status_code == 403
        assert client.get("/openapi.json").status_code == 403

    def test_docs_open_when_debug(self, monkeypatch):
        monkeypatch.setattr(app_config, "DEBUG", True)
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
