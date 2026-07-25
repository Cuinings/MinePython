# -*- coding: utf-8 -*-
"""File batch operations + public app-info tests.

Covers:

  * ``POST /api/files/batch-delete`` — success, forbidden-for-others,
    missing path, empty selection;
  * ``POST /api/files/batch-download`` — success (ZIP returned), byte-cap
    rejection, empty selection;
  * ``GET /api/app-info`` — public branding endpoint.
"""

import io
import os
import sys
import uuid
import zipfile

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


def _upload_one(token: str, name: str, content: bytes = b"hello") -> str:
    r = client.post(
        "/api/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, content)},
        data={"category": "auto"},
    )
    assert r.status_code == 200, r.text
    # The upload response returns the stored ``path`` directly so callers can
    # reference the file for delete / download / install without re-listing
    # (the listing's ``filename`` is the internal safe_name, not the original).
    return r.json()["path"]


class TestBatchDelete:
    def test_success(self):
        token = _admin_token()
        f1 = _upload_one(token, _unique("bd1.txt"))
        f2 = _upload_one(token, _unique("bd2.txt"))
        p1, p2 = f1, f2
        r = client.post(
            "/api/files/batch-delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": [p1, p2]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert set(data["deleted"]) == {p1, p2}
        # They are gone from the listing.
        listing = client.get("/api/files", headers={"Authorization": f"Bearer {token}"}).json()
        assert p1 not in [f["path"] for f in listing["files"]]

    def test_forbidden_for_other_users_file(self):
        admin = _admin_token()
        # Admin uploads a file (owner = admin).
        path = _upload_one(admin, _unique("bd3.txt"))
        # A plain user may not batch-delete it -> ends up in `failed`, file kept.
        uname = _unique("bdu")
        client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin}"},
            json={"username": uname, "password": "testpass", "role": "user", "status": "active"},
        )
        token = client.post("/api/auth/login", json={"username": uname, "password": "testpass"}).json()["token"]
        r = client.post(
            "/api/files/batch-delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": [path]},
        )
        assert r.status_code == 200, r.text
        assert path in [item["path"] for item in r.json()["failed"]]
        assert r.json()["deleted"] == []
        # File record still present.
        listing = client.get("/api/files", headers={"Authorization": f"Bearer {admin}"}).json()
        assert path in [x["path"] for x in listing["files"]]
        # Cleanup.
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {admin}"})

    def test_missing_path_reported(self):
        token = _admin_token()
        r = client.post(
            "/api/files/batch-delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": ["其他/does_not_exist.txt"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == []
        assert r.json()["failed"]

    def test_empty_selection_rejected(self):
        token = _admin_token()
        r = client.post(
            "/api/files/batch-delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": []},
        )
        assert r.status_code == 400


class TestBatchDownload:
    def _upload_two(self, token):
        f1 = _upload_one(token, _unique("dl_a.txt"), b"alpha")
        f2 = _upload_one(token, _unique("dl_b.txt"), b"beta")
        return f1, f2

    def test_success_returns_zip(self):
        token = _admin_token()
        p1, p2 = self._upload_two(token)
        r = client.post(
            "/api/files/batch-download",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": [p1, p2]},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert len(zf.namelist()) == 2
        # Cleanup.
        client.post(
            "/api/files/batch-delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": [p1, p2]},
        )

    def test_byte_cap_exceeded(self, monkeypatch):
        # Patch the name as imported into modules.files.files.
        monkeypatch.setattr("modules.files.files.MAX_BATCH_DOWNLOAD_BYTES", 10)
        token = _admin_token()
        path = _upload_one(token, _unique("bigdl.txt"), b"X" * 100)
        r = client.post(
            "/api/files/batch-download",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": [path]},
        )
        assert r.status_code == 400, r.text
        assert "limit" in r.text.lower()
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})

    def test_empty_selection_rejected(self):
        token = _admin_token()
        r = client.post(
            "/api/files/batch-download",
            headers={"Authorization": f"Bearer {token}"},
            json={"paths": []},
        )
        assert r.status_code == 400


class TestAppInfo:
    def test_public_app_info(self):
        # No auth required.
        r = client.get("/api/app-info")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "name" in data
        assert "version" in data
        assert isinstance(data.get("webadb_bundle_exists"), bool)
