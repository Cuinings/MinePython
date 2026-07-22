# -*- coding: utf-8 -*-
"""P1-6 orphan cleanup + ARCH-7 atomicity + P1-3 preview tests."""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import UPLOAD_DIR
from app.database import File as FileModel
from app.database import SessionLocal, init_db
from app.main import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _upload_one(token: str, name: str, content: bytes, category: str = "auto"):
    r = client.post(
        "/api/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, content)},
        data={"category": category},
    )
    assert r.status_code == 200, r.text
    return r


def _path_of(token: str, name: str) -> str:
    listing = client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
    return next(f["path"] for f in listing.json()["files"] if f["filename"].endswith(name))


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _make_active_user(password: str = "testpass", role: str = "user") -> str:
    token = _admin_token()
    uname = _unique("cln")
    r = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": uname, "password": password, "role": role, "status": "active"},
    )
    assert r.status_code == 200, r.text
    return uname


class TestOrphanCleanup:
    def test_dry_run_reports_disk_orphan(self):
        # Plant a physical file that no DB row references.
        cat = UPLOAD_DIR / "其他"
        cat.mkdir(parents=True, exist_ok=True)
        orphan = cat / f"orphan_{uuid.uuid4().hex[:8]}.txt"
        orphan.write_text("i am an orphan")
        try:
            token = _admin_token()
            r = client.post(
                "/api/admin/cleanup",
                headers={"Authorization": f"Bearer {token}"},
                json={"dry_run": True, "target": "disk"},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["dry_run"] is True
            assert data["disk_orphan_count"] >= 1
            # Dry run must NOT delete the file.
            assert orphan.exists()
        finally:
            orphan.unlink(missing_ok=True)

    def test_real_cleanup_removes_disk_orphan(self):
        cat = UPLOAD_DIR / "其他"
        cat.mkdir(parents=True, exist_ok=True)
        orphan = cat / f"orphan_{uuid.uuid4().hex[:8]}.txt"
        orphan.write_text("delete me")
        token = _admin_token()
        r = client.post(
            "/api/admin/cleanup",
            headers={"Authorization": f"Bearer {token}"},
            json={"dry_run": False, "target": "disk"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["deleted_disk"] >= 1
        assert not orphan.exists()

    def test_cleanup_removes_db_orphan(self):
        # Insert a DB row pointing at a non-existent file.
        ghost_path = f"其他/ghost_{uuid.uuid4().hex[:8]}.txt"
        with SessionLocal() as db:
            db.add(FileModel(filename=ghost_path, category="其他",
                             filepath=ghost_path, size=0,
                             uploaded_by="admin", uploaded_ip=""))
            db.commit()
        token = _admin_token()
        r = client.post(
            "/api/admin/cleanup",
            headers={"Authorization": f"Bearer {token}"},
            json={"dry_run": False, "target": "db"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["deleted_db"] >= 1
        with SessionLocal() as db:
            leftover = db.execute(
                select(FileModel).where(FileModel.filepath == ghost_path)
            ).scalar_one_or_none()
            assert leftover is None

    def test_cleanup_requires_admin(self):
        # A plain user (not admin) must be refused.
        uname = _make_active_user(role="user")
        r = client.post(
            "/api/auth/login", json={"username": uname, "password": "testpass"}
        )
        tok = r.json()["token"]
        r2 = client.post(
            "/api/admin/cleanup",
            headers={"Authorization": f"Bearer {tok}"},
            json={"dry_run": True},
        )
        assert r2.status_code == 403, r2.text


class TestAtomicDelete:
    def test_delete_removes_both_record_and_file(self):
        """ARCH-7: after delete, the DB row AND the physical file are gone."""
        token = _admin_token()
        upload = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("atomic_del.txt", b"payload")},
            data={"category": "auto"},
        )
        assert upload.status_code == 200, upload.text

        # The stored path is the DB filepath (category/safe_name), NOT the
        # original filename. Resolve it from the file list endpoint.
        listing = client.get(
            "/api/files", headers={"Authorization": f"Bearer {token}"}
        )
        assert listing.status_code == 200, listing.text
        path = next(
            f["path"] for f in listing.json()["files"]
            if f["filename"].endswith("atomic_del.txt")
        )
        full = UPLOAD_DIR / path
        assert full.exists()

        d = client.delete(
            f"/api/files/{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert d.status_code == 200, d.text
        # Physical file removed.
        assert not full.exists()
        # DB record removed (no phantom row).
        with SessionLocal() as db:
            row = db.execute(
                select(FileModel).where(FileModel.filepath == path)
            ).scalar_one_or_none()
            assert row is None


class TestFilePreview:
    def test_preview_returns_inline_with_mime(self):
        token = _admin_token()
        _upload_one(token, "preview_me.png", b"\x89PNG\r\n\x1a\n fake", category="图片")
        path = _path_of(token, "preview_me.png")

        r = client.get(
            f"/api/preview/{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        # Inline disposition so the browser renders in place.
        assert "inline" in r.headers.get("content-disposition", "")
        # Correct MIME for a .png.
        assert r.headers["content-type"].startswith("image/png")
        assert r.content == b"\x89PNG\r\n\x1a\n fake"

    def test_preview_guest_and_missing(self):
        token = _admin_token()
        _upload_one(token, "preview_guest.png", b"guest-ok", category="图片")
        path = _path_of(token, "preview_guest.png")

        # Guest (no token) may preview too — same guest policy as /download.
        r = client.get(f"/api/preview/{path}")
        assert r.status_code == 200, r.text
        assert "inline" in r.headers.get("content-disposition", "")

        # A path that does not exist returns 404, not 200.
        r2 = client.get("/api/preview/图片/does_not_exist.png")
        assert r2.status_code == 404, r2.text
