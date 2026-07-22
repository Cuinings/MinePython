# -*- coding: utf-8 -*-
"""P1-7 大文件上传进度条 — backend contract tests.

The browser half of P1-7 is the XHR ``upload.onprogress`` bar in ``files.html``
(already implemented: ``uploadFiles`` builds a single ``XMLHttpRequest`` and
updates ``#progressBar`` / ``#progressPct`` on each progress event). These tests
lock in the *server-side* contract that makes that bar meaningful:

  * a large (multi-MB) file uploads in one request and is stored with its real
    size, so the bar's 0->100% maps to a request that actually completes;
  * the configured size ceiling genuinely rejects oversized uploads, so the bar
    never spins on a doomed request (the endpoint fails fast with 400).

``file_service`` reads the ceiling dynamically from ``modules.user.config`` (ARCH-8),
so we can shrink it in a test without touching production values.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from modules.user.config import MAX_UPLOAD_SIZE_BYTES
from modules.user.database import init_db
from modules.combined import app
from modules.files.services.file_service import validate_upload

# Tables + RBAC seed before any request (mirrors test_api.py).
init_db()
client = TestClient(app)


def _admin_token() -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _stored_path(token: str, original_name: str) -> str:
    resp = client.get(
        f"/api/files?search={original_name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    for f in resp.json()["files"]:
        if original_name in f["filename"]:
            return f["path"]
    raise AssertionError(f"uploaded file {original_name} not found in listing")


class TestLargeUpload:
    def test_large_file_upload_succeeds_and_stores_real_size(self):
        """A multi-MB single upload completes and is persisted with exact size."""
        token = _admin_token()
        name = f"big_{uuid.uuid4().hex[:8]}.bin"
        payload = os.urandom(5 * 1024 * 1024)  # 5 MiB

        resp = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (name, payload)},
            data={"category": "auto"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        # size reported by the API equals the bytes we sent.
        assert body["size"] == len(payload)

        # The record actually landed and the physical file exists at full size.
        path = _stored_path(token, name)
        assert path
        from modules.user.config import UPLOAD_DIR

        full = UPLOAD_DIR / path
        assert full.exists()
        assert full.stat().st_size == len(payload)

    def test_oversize_upload_rejected_via_ceiling(self, monkeypatch):
        """The config ceiling rejects an upload whose size exceeds it (400).

        Drives the real endpoint with a shrunken ceiling so the test is cheap.
        """
        token = _admin_token()
        # Shrink the limit to 1 KiB for this test only.
        monkeypatch.setattr("modules.user.config.MAX_UPLOAD_SIZE_BYTES", 1024)
        small_ceiling = 1024

        name = f"toobig_{uuid.uuid4().hex[:8]}.bin"
        payload = os.urandom(small_ceiling + 4096)  # just over the ceiling

        resp = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (name, payload)},
            data={"category": "auto"},
        )
        assert resp.status_code == 400, resp.text
        assert "max size" in resp.text.lower()

    def test_validate_upload_ceiling_invariant(self):
        """Unit-level: validate_upload raises exactly at the configured ceiling."""
        # At (or below) the ceiling it is a no-op.
        validate_upload("ok.pdf", MAX_UPLOAD_SIZE_BYTES)
        # One byte over -> 400.
        with pytest.raises(Exception) as exc:
            validate_upload("toobig.pdf", MAX_UPLOAD_SIZE_BYTES + 1)
        # FastAPI's HTTPException carries status_code 400.
        assert getattr(exc.value, "status_code", None) == 400
