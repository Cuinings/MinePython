# -*- coding: utf-8 -*-
"""Isolate the test suite from the real server.db AND the real uploads dir.

Set DB_PATH and UPLOAD_DIR to throwaway locations BEFORE any app module is
imported, so tests never touch (or pollute) the production database or the
real ``uploads/`` directory — and so bulk-cleanup tests don't trip the
environment's safe-delete guard on a populated uploads folder.
"""
import os
import tempfile
from pathlib import Path

import pytest

_TEST_DB = os.path.join(tempfile.gettempdir(), "fileserver_pytest.db")
for _f in (f"{_TEST_DB}", f"{_TEST_DB}-wal", f"{_TEST_DB}-shm"):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass
os.environ["DB_PATH"] = _TEST_DB

# Isolate uploads in a temp dir. Patch the config module's UPLOAD_DIR *before*
# any app module imports it, so the copied references in files/categories/
# cleanup all pick up the temp path.
_TEST_UPLOADS = Path(tempfile.gettempdir()) / "fileserver_pytest_uploads"
_TEST_UPLOADS.mkdir(parents=True, exist_ok=True)
import modules.user.config as _cfg
_cfg.UPLOAD_DIR = _TEST_UPLOADS

# --- Deterministic knobs for the security/edge tests (read at import time) ---
# Neutralize the per-IP login throttle for endpoint tests (they all share the
# TestClient's single client IP); the IP-throttle logic is exercised directly
# via its helper functions instead. Per-username lock keeps its default of 5.
os.environ.setdefault("LOGIN_IP_MAX_FAILS", "100000")
# Small batch-download file cap so the limit is cheap to trigger in a test.
os.environ.setdefault("MAX_BATCH_DOWNLOAD_FILES", "5")


@pytest.fixture(autouse=True)
def _reset_upload_rate_limit():
    """Isolate the in-memory per-user upload rate limiter between tests.

    ``test_rate_setting`` (in test_upload_security.py) mutates the process-wide
    ``config.UPLOAD_RATE_LIMIT`` global to a non-zero value and never restores
    it, which would otherwise trip every later upload in the same process with
    a 429 — spurious failures unrelated to the code under test. Reset it (and
    the sliding-window counter) after each test so the suite is hermetic.
    """
    yield
    import modules.user.config as _cfg

    _cfg.UPLOAD_RATE_LIMIT = 0
    try:
        import modules.files.services.file_service as _fs

        _fs._UPLOAD_COUNTS.clear()
    except Exception:  # pragma: no cover - defensive
        pass

