# -*- coding: utf-8 -*-
"""Category management tests (``category:manage`` gated).

Covers the two endpoints that had no automated coverage:

  * ``DELETE /api/categories/{name}`` — removes every file in the category
    (DB record + physical file + directory);
  * ``POST  /api/organize`` — moves scattered files in the uploads root into
    their proper category folders by extension.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from modules.user.config import UPLOAD_DIR
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


class TestDeleteCategory:
    def test_delete_removes_files_and_dir(self):
        token = _admin_token()
        cat = _unique("cat")
        # Upload a file directly into this (new) category.
        up = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cfile.txt", b"data")},
            data={"category": cat},
        )
        assert up.status_code == 200, up.text
        # The category now appears in the listing with >= 1 file.
        cats = client.get("/api/categories", headers={"Authorization": f"Bearer {token}"}).json()["categories"]
        assert any(c["category"] == cat for c in cats)

        # Delete the category.
        r = client.delete(f"/api/categories/{cat}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

        # Gone from the listing, and the physical dir is removed.
        cats = client.get("/api/categories", headers={"Authorization": f"Bearer {token}"}).json()["categories"]
        assert not any(c["category"] == cat for c in cats)
        assert not (UPLOAD_DIR / cat).exists()

    def test_non_admin_forbidden(self):
        # A plain user lacks category:manage.
        admin = _admin_token()
        uname = _unique("catu")
        client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin}"},
            json={"username": uname, "password": "testpass", "role": "user", "status": "active"},
        )
        token = client.post("/api/auth/login", json={"username": uname, "password": "testpass"}).json()["token"]
        r = client.delete("/api/categories/文档", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
        client.delete(
            f"/api/admin/users/{_user_id(admin, uname)}",
            headers={"Authorization": f"Bearer {admin}"},
        )


def _user_id(admin_token: str, username: str) -> int:
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    for u in resp.json()["users"]:
        if u["username"] == username:
            return u["id"]
    raise AssertionError(f"user {username} not found")


class TestOrganizeRoot:
    def test_organize_moves_root_files(self):
        token = _admin_token()
        # Plant a loose file directly in the uploads root (the upload endpoint
        # would otherwise always place files inside a category subdir).
        root_file = UPLOAD_DIR / f"loose_{uuid.uuid4().hex[:8]}.txt"
        root_file.write_text("orphaned in root")
        try:
            assert root_file.exists()
            r = client.post("/api/organize", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            # The file is no longer in the root...
            assert not root_file.exists()
            # ...and now lives under its category folder (文档 for .txt).
            dest = UPLOAD_DIR / "文档" / root_file.name
            assert dest.exists(), f"expected {dest} after organize"
        finally:
            root_file.unlink(missing_ok=True)
            (UPLOAD_DIR / "文档" / root_file.name).unlink(missing_ok=True)

    def test_organize_noop_when_empty(self):
        token = _admin_token()
        r = client.post("/api/organize", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert "No files" in r.json().get("message", "")
