# -*- coding: utf-8 -*-
"""ADB one-click-install endpoint tests (``file:adb_install`` gated).

The real endpoints shell out to the host ``adb`` binary, which is not available
in CI and may not even be installed. These tests stub the two module-level
collaborators — ``modules.files.adb._run_adb`` and
``modules.files.adb._list_ready_devices`` — so the HTTP-layer behaviour
(path validation, permission gating, device-selection branching, error
messages) is exercised deterministically without a device or a real adb.

Verified:

  * ``GET  /api/adb/devices`` — 401 without auth; ``adb_missing`` surfaced when
    adb is absent; parsed device list when present;
  * ``POST /api/adb/install`` — rejects non-``.apk`` / path-traversal / missing
    files; branches to ``needs_device`` / ``needs_serial``; succeeds when a
    ready device is available;
  * ``POST /api/adb/connect`` / ``disconnect`` — host validation + success.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import modules.files.adb as adb
from modules.user.database import init_db
from modules.combined import app

init_db()
client = TestClient(app)


def _admin_token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _unique(name: str) -> str:
    import uuid

    # Preserve the extension so files keep a recognizable suffix (e.g.
    # ``inst.apk`` -> ``inst_a1b2c3d4.apk``); the install endpoint rejects
    # anything whose suffix isn't ``.apk``.
    stem, dot, ext = name.rpartition(".")
    if dot:
        return f"{stem}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"{name}_{uuid.uuid4().hex[:8]}"


def _upload_apk(token: str, name: str) -> str:
    r = client.post(
        "/api/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (name, b"PK\x03\x04 fake apk bytes")},
        data={"category": "auto"},
    )
    assert r.status_code == 200, r.text
    # The upload response returns the stored path directly — no listing lookup
    # needed (the listing's filename is the internal safe_name, not the
    # original name the installer expects to match on).
    return r.json()["path"]


def _make_run(stdout_map=None):
    """Build a fake ``_run_adb`` that returns CompletedProcesses on request."""

    def fake_run(args, timeout=30):
        if args[:2] == ["devices", "-l"]:
            return subprocess.CompletedProcess(
                args, 0, stdout="List of devices attached\nABC123  device  model:Pixel\n", stderr=""
            )
        if args[:1] == ["version"] or args[0] == "version":
            return subprocess.CompletedProcess(args, 0, stdout="Android Debug Bridge 1.0\n", stderr="")
        if len(args) >= 2 and args[0] == "-s" and "install" in args:
            return subprocess.CompletedProcess(args, 0, stdout="Performing Streamed Install\nSuccess\n", stderr="")
        if args and args[0] in ("connect", "disconnect"):
            return subprocess.CompletedProcess(args, 0, stdout=f"{args[-1]} ok\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return fake_run


class TestDevices:
    def test_no_auth_401(self):
        r = client.get("/api/adb/devices")
        assert r.status_code == 401

    def test_adb_missing_reported(self, monkeypatch):
        def fake_missing(args, timeout=30):
            if args[:2] == ["devices", "-l"]:
                return None  # adb not found
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        monkeypatch.setattr(adb, "_run_adb", fake_missing)
        token = _admin_token()
        r = client.get("/api/adb/devices", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert r.json()["adb_missing"] is True
        assert r.json()["devices"] == []

    def test_devices_parsed(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.get("/api/adb/devices", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["adb_missing"] is False
        assert data["devices"]
        assert data["devices"][0]["serial"] == "ABC123"
        assert data["devices"][0]["ready"] is True


class TestInstall:
    def test_non_apk_rejected(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        up = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("note.txt", b"plain")},
            data={"category": "auto"},
        )
        path = up.json()["path"]
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": path},
        )
        assert r.status_code == 400, r.text
        assert "apk" in r.text.lower()
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})

    def test_path_traversal_rejected(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": "../escape.apk"},
        )
        assert r.status_code == 400, r.text
        assert "非法" in r.text

    def test_missing_file_404(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": "安装包/does_not_exist.apk"},
        )
        assert r.status_code == 404, r.text

    def test_needs_device(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        monkeypatch.setattr(adb, "_list_ready_devices", lambda: [])
        token = _admin_token()
        path = _upload_apk(token, _unique("inst.apk"))
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": path},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("needs_device") is True
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})

    def test_needs_serial(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        monkeypatch.setattr(
            adb,
            "_list_ready_devices",
            lambda: [
                {"serial": "DEV1", "state": "device", "model": "A", "ready": True},
                {"serial": "DEV2", "state": "device", "model": "B", "ready": True},
            ],
        )
        token = _admin_token()
        path = _upload_apk(token, _unique("inst.apk"))
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": path},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("needs_serial") is True
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})

    def test_install_success(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        monkeypatch.setattr(
            adb,
            "_list_ready_devices",
            lambda: [{"serial": "ABC123", "state": "device", "model": "Pixel", "ready": True}],
        )
        token = _admin_token()
        path = _upload_apk(token, _unique("inst.apk"))
        r = client.post(
            "/api/adb/install",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": path},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["serial"] == "ABC123"
        assert data["returncode"] == 0
        client.delete(f"/api/files/{path}", headers={"Authorization": f"Bearer {token}"})


class TestConnectDisconnect:
    def test_invalid_host_rejected(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.post(
            "/api/adb/connect",
            headers={"Authorization": f"Bearer {token}"},
            json={"host": "bad host!!", "port": 5555},
        )
        assert r.status_code == 400, r.text

    def test_connect_success(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.post(
            "/api/adb/connect",
            headers={"Authorization": f"Bearer {token}"},
            json={"host": "192.168.1.10", "port": 5555},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert r.json()["target"] == "192.168.1.10:5555"

    def test_disconnect_success(self, monkeypatch):
        monkeypatch.setattr(adb, "_run_adb", _make_run())
        token = _admin_token()
        r = client.post(
            "/api/adb/disconnect",
            headers={"Authorization": f"Bearer {token}"},
            json={"host": "192.168.1.10", "port": 5555},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
