import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


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


print("=== 1. admin login ===")
st, admin_token = login("admin", "admin123")
assert st == 200 and admin_token, f"admin login failed: {st}"
print("  admin token OK")

print("=== 2. GET /api/auth/me (shape) ===")
st, d = req("GET", "/api/auth/me", admin_token)
assert st == 200 and "permissions" in d and "role" in d, d
print("  me:", d.get("username"), d.get("role"), "perms:", len(d.get("permissions", [])))

print("=== 3. PUT /api/auth/me nickname-only (session kept) ===")
st, d = req("PUT", "/api/auth/me", admin_token, {"nickname": "AdminRenamed"})
assert st == 200 and d.get("ok"), d
assert d.get("password_changed") is not True, "nickname-only must NOT flag password_changed"
print("  update ok, password_changed=", d.get("password_changed"))
st, d = req("GET", "/api/auth/me", admin_token)
assert d.get("nickname") == "AdminRenamed", d
print("  nickname now:", d.get("nickname"))
# revert
req("PUT", "/api/auth/me", admin_token, {"nickname": "admin"})

print("=== 4. PUT /api/auth/me with password (forces re-login) ===")
st, d = req("PUT", "/api/auth/me", admin_token,
            {"nickname": "admin", "old_password": "admin123", "new_password": "admin123"})
assert st == 200 and d.get("password_changed") is True, d
print("  password change flagged, password_changed=", d.get("password_changed"))
# re-login with same password (unchanged value) to refresh token
st, admin_token = login("admin", "admin123")
assert st == 200, "re-login after pw change failed"

print("=== 5. register + approve a normal user ===")
st, d = req("POST", "/api/auth/register", body={"username": "uctest01", "password": "uctest01", "nickname": "UC Tester"})
print("  register:", st, d.get("message"))
st, d = req("GET", "/api/admin/users", admin_token)
uid = next((u["id"] for u in d.get("users", []) if u["username"] == "uctest01"), None)
assert uid, "uctest01 not found in admin list"
req("PUT", f"/api/admin/users/{uid}/approve", admin_token)
st, user_token = login("uctest01", "uctest01")
assert st == 200 and user_token, "uctest01 login failed after approve"
print("  uctest01 approved + logged in, role=", d.get("role"))

print("=== 6. normal user: GET /api/auth/me + PUT profile ===")
st, d = req("GET", "/api/auth/me", user_token)
assert st == 200, d
st, d = req("PUT", "/api/auth/me", user_token, {"nickname": "UC Renamed"})
assert st == 200 and d.get("ok") and d.get("password_changed") is not True, d
print("  normal user profile update OK")

print("=== 7. normal user CANNOT open admin user list (403) ===")
st, d = req("GET", "/api/admin/users", user_token)
assert st == 403, f"expected 403, got {st}"
print("  admin list blocked for normal user (403) OK")

print("=== 8. normal user deactivate own account ===")
st, d = req("POST", "/api/auth/me/deactivate", user_token)
assert st == 200 and d.get("ok"), d
print("  deactivate OK:", d.get("message"))
st, d = req("GET", "/api/auth/me", user_token)
assert st == 401, f"deactivated token should be 401, got {st}"
print("  deactivated token now rejected (401) OK")

print("=== 9. cleanup test user ===")
req("DELETE", f"/api/admin/users/{uid}", admin_token)
print("  test user removed")

print("\nALL BACKEND CHECKS PASSED")
