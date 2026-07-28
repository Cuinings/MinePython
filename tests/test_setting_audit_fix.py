# -*- coding: utf-8 -*-
"""Regression test for update-setting audit parameter order (admin.py L214/L246/L304).

Background
----------
`_audit_log` is defined as ``_audit_log(action, target, username, ip)``.
The three "update setting" call sites used to pass arguments in the wrong
order (``action, username, target, ip``), so the operator name landed in the
`target` column and the changed value landed in the `username` column. That
produced the abnormal audit rows where the operator column was empty/garbled
and the target column showed "admin".

These tests verify the fix: after a setting change, the audit row must store
the OPERATOR in `username` and the CHANGED VALUE in `target`.

To avoid permanently mutating real .env config, each test restores the
previous value in a finally-block. The backing server.db is also restored by
the test runner's cleanup, but the assertions here are the real guarantee.
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from modules.user import config
from modules.user.database import init_db
from modules.combined import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_update_setting_audit_attribution():
    token = _admin_token()
    original = config.get_max_user_upload_mb()
    new_val = (original if isinstance(original, int) else 0) + 7
    try:
        r = client.put(
            "/api/admin/setting/max_user_upload_mb",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": new_val},
        )
        assert r.status_code == 200, r.text

        logs = client.get(
            "/api/audit/logs?action=update_setting",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["logs"]
        row = next((x for x in logs if x["action"] == "update_setting"), None)
        assert row is not None, "no update_setting audit row produced"
        # Operator must be in `username`, not `target`.
        assert row["username"] == "admin", f"username should be 'admin', got {row['username']!r}"
        # The changed value must be in `target`.
        assert row["target"].startswith("max_user_upload_mb="), (
            f"target should start with setting key, got {row['target']!r}"
        )
        # Username must NOT leak into target (the original bug symptom).
        assert "admin" not in row["target"], f"operator leaked into target: {row['target']!r}"
    finally:
        config.set_max_user_upload_mb(original)


def test_update_site_audit_attribution():
    token = _admin_token()
    original = config.APP_NAME
    name = f"site_{uuid.uuid4().hex[:6]}"
    try:
        r = client.put(
            "/api/admin/site",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name},
        )
        assert r.status_code == 200, r.text

        logs = client.get(
            "/api/audit/logs?action=update_site",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["logs"]
        row = next((x for x in logs if x["action"] == "update_site"), None)
        assert row is not None, "no update_site audit row produced"
        assert row["username"] == "admin", f"username should be 'admin', got {row['username']!r}"
        assert row["target"] == name, f"target should be the new site name, got {row['target']!r}"
        assert "admin" not in row["target"], f"operator leaked into target: {row['target']!r}"
    finally:
        config.set_app_name(original)


def test_update_upload_limit_audit_attribution():
    token = _admin_token()
    original = config.get_max_upload_size_mb()
    new_val = (original if isinstance(original, int) else 100) + 11
    try:
        r = client.put(
            "/api/admin/upload-limit",
            headers={"Authorization": f"Bearer {token}"},
            json={"max_upload_size_mb": new_val},
        )
        assert r.status_code == 200, r.text

        logs = client.get(
            "/api/audit/logs?action=update_upload_limit",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["logs"]
        row = next((x for x in logs if x["action"] == "update_upload_limit"), None)
        assert row is not None, "no update_upload_limit audit row produced"
        assert row["username"] == "admin", f"username should be 'admin', got {row['username']!r}"
        assert row["target"] == f"{new_val}MB", (
            f"target should be '<n>MB', got {row['target']!r}"
        )
        assert "admin" not in row["target"], f"operator leaked into target: {row['target']!r}"
    finally:
        config.set_max_upload_size_mb(original)
