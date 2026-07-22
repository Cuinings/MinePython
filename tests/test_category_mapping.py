# -*- coding: utf-8 -*-
"""P1-4 分类映射配置化 — backend tests.

Verifies the extension -> category mapping moved from the hardcoded
``app.config.EXT_CATEGORY`` dict into a DB table that is editable at runtime via
the category-mapping CRUD API (admin, ``category:manage``):

  * the mapping is seeded from EXT_CATEGORY on first boot and listed via the API;
  * PUT creates/updates a rule and the change takes effect on the next upload
    (DB-backed, cache-busted);
  * DELETE removes a rule;
  * non-admins (e.g. uploader) are refused 403.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.main import app
from app.services.category_service import categorize

init_db()
client = TestClient(app)


def _admin_token() -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _uploader_token() -> str:
    """Create (admin) + login an uploader so we can assert 403 on admin APIs."""
    uname = f"up_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {_admin_token()}"},
        json={"username": uname, "password": "up123456", "role": "uploader", "status": "active"},
    )
    assert r.status_code == 200, r.text
    resp = client.post("/api/auth/login", json={"username": uname, "password": "up123456"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


class TestCategoryMapping:
    def test_mapping_seeded_and_listed(self):
        token = _admin_token()
        resp = client.get(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        rules = resp.json()["rules"]
        # Seeded from EXT_CATEGORY: e.g. ".pdf" -> "文档".
        by_ext = {r["extension"]: r["category"] for r in rules}
        assert by_ext.get(".pdf") == "文档"
        assert by_ext.get(".jpg") == "图片"

    def test_upsert_then_effective_on_upload(self):
        token = _admin_token()
        # Add a brand-new extension -> category rule.
        put = client.put(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
            json={"extension": ".xyz", "category": "代码"},
        )
        assert put.status_code == 200, put.text
        assert any(r["extension"] == ".xyz" and r["category"] == "代码"
                   for r in put.json()["rules"])

        # The new rule takes effect on a real upload classified as 'auto'.
        name = f"sample_{uuid.uuid4().hex[:8]}.xyz"
        up = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (name, b"hello")},
            data={"category": "auto"},
        )
        assert up.status_code == 200, up.text
        assert up.json()["category"] == "代码"

    def test_delete_rule(self):
        token = _admin_token()
        # Ensure it exists first.
        client.put(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
            json={"extension": ".zzz", "category": "文档"},
        )
        # Delete it.
        d = client.delete(
            "/api/categories/mapping/.zzz",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert d.status_code == 200, d.text
        # And it is gone from the listing.
        listing = client.get(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["rules"]
        assert not any(r["extension"] == ".zzz" for r in listing)

    def test_delete_missing_rule_404(self):
        token = _admin_token()
        d = client.delete(
            "/api/categories/mapping/.nope",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert d.status_code == 404

    def test_non_admin_forbidden(self):
        token = _uploader_token()
        r = client.get(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        r = client.put(
            "/api/categories/mapping",
            headers={"Authorization": f"Bearer {token}"},
            json={"extension": ".abc", "category": "文档"},
        )
        assert r.status_code == 403

    def test_categorize_unknown_falls_back_to_default(self):
        """An unmapped extension returns the default category (DB-backed)."""
        with SessionLocal() as db:
            cat = categorize("weirdfile.qwx", db)
        assert cat == "其他"
