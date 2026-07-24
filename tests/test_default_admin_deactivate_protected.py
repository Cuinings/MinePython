# -*- coding: utf-8 -*-
"""Regression test for the requirement:

    默认内置管理源账号不支持注销；此账号下所有注销入口隐藏；其他账号不受影响

Backend enforcement (defense-in-depth behind the UI hiding done in
files.html / users.html):

  * The seeded default admin account (``is_default = True``) MUST be rejected
    when it tries to deactivate itself via ``POST /api/auth/me/deactivate``
    (HTTP 400, "默认账号不可注销"), and it MUST stay active afterwards.
  * A normal (non-default) user MUST still be able to deactivate their own
    account (HTTP 200) — proving the protection is scoped to the default
    account only ("其他账号不受影响").

Run against a live server (assumes the app is up on :8000 with the seeded
default admin, e.g. ``admin`` / ``admin123``):

    python tests/test_default_admin_deactivate_protected.py

Mirrors the live-server style of ``tests/test_ucenter_smoke.py``.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
DEFAULT_ADMIN = "admin"
DEFAULT_ADMIN_PW = "admin123"


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def login(user, pw):
    st, d = req("POST", "/api/auth/login", body={"username": user, "password": pw})
    return st, d.get("token")


def main():
    print("=== A. default admin login ===")
    st, admin_token = login(DEFAULT_ADMIN, DEFAULT_ADMIN_PW)
    assert st == 200 and admin_token, f"default admin login failed: {st}"
    print("  default admin token OK")

    print("=== B. default admin is flagged is_default ===")
    st, d = req("GET", "/api/auth/me", admin_token)
    assert st == 200 and d.get("is_default") is True, f"expected is_default=True, got {d}"
    print("  is_default =", d.get("is_default"))

    print("=== C. default admin CANNOT deactivate itself (expect 400) ===")
    st, d = req("POST", "/api/auth/me/deactivate", admin_token)
    assert st == 400, f"default admin deactivate should be 400, got {st}: {d}"
    detail = d.get("detail", "")
    assert "默认" in detail or "注销" in detail, f"unexpected rejection message: {d}"
    print("  rejected:", st, detail)

    print("=== C2. default admin STILL active after the rejected deactivate ===")
    st, d = req("GET", "/api/auth/me", admin_token)
    assert st == 200 and d.get("status") == "active", f"default admin must remain active: {d}"
    print("  still active, status =", d.get("status"))

    print("=== D. create + approve a normal (non-default) user ===")
    uname, upw = "daptest01", "daptest01"
    req("POST", "/api/auth/register",
        body={"username": uname, "password": upw, "nickname": "DA Tester"})
    st, d = req("GET", "/api/admin/users", admin_token)
    uid = next((u["id"] for u in d.get("users", []) if u["username"] == uname), None)
    assert uid, "daptest01 not found in admin list"
    req("PUT", f"/api/admin/users/{uid}/approve", admin_token)
    st, user_token = login(uname, upw)
    assert st == 200 and user_token, f"normal user login failed: {st}"
    print("  normal user logged in, is_default =",
          req("GET", "/api/auth/me", user_token)[1].get("is_default"))

    print("=== E. normal user CAN deactivate (other accounts unaffected) ===")
    st, d = req("POST", "/api/auth/me/deactivate", user_token)
    assert st == 200 and d.get("ok"), f"normal user deactivate should succeed: {st} {d}"
    print("  normal user deactivated OK:", d.get("message"))

    print("=== F. cleanup: delete the test user ===")
    st, d = req("DELETE", f"/api/admin/users/{uid}", admin_token)
    assert st == 200 and d.get("ok"), f"cleanup delete failed: {st} {d}"
    print("  test user removed")

    print("\nALL DEFAULT-ADMIN DEACTIVATE-PROTECTION CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAILED:", e)
        sys.exit(1)
