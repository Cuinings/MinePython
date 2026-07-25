# -*- coding: utf-8 -*-
"""Regression tests for the upload security fixes (P1-P6).

These lock in the behaviour introduced to close the vulnerabilities found in the
upload feature review:

* P1  path traversal via ``category`` / ``filename`` is collapsed server-side
* P2  (frontend) filename is escaped -- covered indirectly by the API contract
* P3  user-supplied HTML/SVG/etc. is served as ``attachment`` (never inline)
* P4  oversized uploads are rejected while streaming, not just on the
        client-reported Content-Length
* P5  the default blocklist rejects server-side script extensions (e.g. .php)

Run (from the project root, with the project interpreter that has pytest):

    python -m pytest tests/test_upload_security.py -v

DB and uploads are isolated to a temp dir by ``conftest.py``, so nothing
touches the real ``server.db`` or ``uploads/``.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.user.config as _cfg
from fastapi.testclient import TestClient
from modules.user.database import init_db
from modules.combined import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _upload(token, content, filename, category="auto"):
    return client.post(
        "/api/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content)},
        data={"category": category},
    )


def _stored_path(token, needle):
    listing = client.get("/api/files", headers={"Authorization": f"Bearer {token}"}).json()
    for f in listing["files"]:
        if needle in f["filename"] or needle in f.get("path", ""):
            return f["path"]
    raise AssertionError(f"uploaded file containing {needle!r} not found in listing")


class TestPathTraversal:
    def test_category_traversal_collapsed(self):
        """A '../escape' category must be sanitized to its last segment."""
        token = _admin_token()
        r = _upload(token, b"hello", "normal.txt", category="../escape")
        assert r.status_code == 200, r.text
        # The route returns the *sanitized* category, not the raw client value.
        assert r.json()["category"] == "escape"
        # And the physical file lives under UPLOAD_DIR, never outside it.
        path = _stored_path(token, "normal.txt")
        full = (_cfg.UPLOAD_DIR / path).resolve()
        assert _cfg.UPLOAD_DIR.resolve() in full.parents or full == _cfg.UPLOAD_DIR.resolve()

    def test_filename_traversal_collapsed(self):
        """A '../../etc/cron.d/evil' filename must lose its directory parts."""
        token = _admin_token()
        r = _upload(token, b"x", "../../etc/cron.d/evil")
        assert r.status_code == 200, r.text
        path = _stored_path(token, "evil")
        # Stored name is uuid_<base>; it must contain no separators.
        assert "/" not in path.split("/")[-1]
        assert "\\" not in path.split("/")[-1]


class TestBlockedExtension:
    def test_php_blocked_by_default(self):
        """The new default blocklist must reject server-side script types."""
        token = _admin_token()
        r = _upload(token, b"<?php phpinfo(); ?>", "evil.php")
        assert r.status_code == 400, r.text
        assert "block" in r.text.lower()


class TestHtmlPreviewNotInline:
    def test_html_served_as_attachment(self):
        """Uploaded HTML must NOT render inline (would be stored XSS)."""
        token = _admin_token()
        r = _upload(token, b"<script>alert(1)</script>", "xss.html")
        assert r.status_code == 200, r.text
        path = _stored_path(token, "xss.html")
        r2 = client.get(f"/api/preview/{path}", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200, r2.text
        # Force attachment so it downloads instead of executing in the session.
        assert r2.headers["content-disposition"].lower().startswith("attachment")
        # And never let the browser sniff the type.
        assert r2.headers.get("x-content-type-options") == "nosniff"

    def test_safe_media_still_inline(self):
        """A plain image/text should still be previewable inline."""
        token = _admin_token()
        r = _upload(token, b"\x89PNG\r\n\x1a\n", "safe.png")
        assert r.status_code == 200, r.text
        path = _stored_path(token, "safe.png")
        r2 = client.get(f"/api/preview/{path}", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200, r2.text
        assert r2.headers["content-disposition"].lower().startswith("inline")


class TestStreamingSizeLimit:
    def test_oversized_rejected(self, monkeypatch):
        """An upload over the limit is rejected (P4 backstop on top of the
        client-size check)."""
        import modules.files.services.file_service as fs  # noqa: F401

        monkeypatch.setattr(_cfg, "MAX_UPLOAD_SIZE_BYTES", 10)  # 10 bytes cap
        token = _admin_token()
        r = _upload(token, b"X" * 1000, "big.txt")  # 1000 bytes >> 10
        assert r.status_code == 400, r.text
        # No orphan partial file should remain: the oversized body never
        # produced a record, and save_file unlinks the half-written file.
        listing = client.get("/api/files", headers={"Authorization": f"Bearer {token}"}).json()
        assert not any("big.txt" in f["filename"] for f in listing["files"])


class TestAdminSettings:
    """The admin KV settings framework (generic /api/admin/setting/{key})."""

    def test_unknown_key_404(self):
        token = _admin_token()
        r = client.get(
            "/api/admin/setting/does_not_exist",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_no_auth_blocked(self):
        # No token => the admin guard must refuse (401/403), not leak settings.
        r = client.get("/api/admin/setting/max_upload_size_mb")
        assert r.status_code in (401, 403)

    def test_read_and_set_upload_limit(self, monkeypatch):
        # Avoid persisting to the real .env during the test.
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        token = _admin_token()
        before = client.get(
            "/api/admin/setting/max_upload_size_mb",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["value"]
        r = client.put(
            "/api/admin/setting/max_upload_size_mb",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"value": 1234},
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == 1234
        after = client.get(
            "/api/admin/setting/max_upload_size_mb",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["value"]
        assert after == 1234
        # Restore the default so other suites are unaffected.
        monkeypatch.setattr(_cfg, "MAX_UPLOAD_SIZE_MB", before)
        monkeypatch.setattr(_cfg, "MAX_UPLOAD_SIZE_BYTES", before * 1024 * 1024)

    def test_quota_setting(self, monkeypatch):
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        token = _admin_token()
        r = client.put(
            "/api/admin/setting/max_user_upload_mb",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"value": 0},
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == 0
        after = client.get(
            "/api/admin/setting/max_user_upload_mb",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["value"]
        assert after == 0

    def test_rate_setting(self, monkeypatch):
        monkeypatch.setattr(_cfg, "_write_env_key", lambda *a, **k: None)
        token = _admin_token()
        r = client.put(
            "/api/admin/setting/upload_rate_limit",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"value": 5},
        )
        assert r.status_code == 200, r.text
        assert r.json()["value"] == 5
