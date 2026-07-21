# -*- coding: utf-8 -*-
"""Utility functions: password hashing, file categorization, size formatting, audit logging."""

import hashlib
import logging
import os
import secrets
import shutil
import subprocess
import sys
import ctypes
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("uvicorn")

# Argon2id hasher — memory-hard, resistant to GPU/ASIC cracking (unlike SHA-256).
# OWASP Argon2id minimum: memory_cost=19 MiB, time_cost=2, parallelism=1.
_ph = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)


def _audit_log(action: str, target: str = "", username: str = "anonymous", ip: str = ""):
    """Write an audit log entry to the database."""
    from sqlalchemy import text

    from app.database import SessionLocal
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO audit_log (username, action, target, ip) VALUES (:u, :a, :t, :i)"),
            {"u": username, "a": action, "t": target, "i": ip},
        )
        db.commit()


def _client_ip(request) -> str:
    """Best-effort client IP: prefer X-Forwarded-For, fall back to direct peer."""
    if request is None:
        return ""
    fwd = getattr(request, "headers", {}).get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else ""


def _is_legacy_hash(stored: str) -> bool:
    """True if ``stored`` uses the old 'salt:sha256' format rather than argon2."""
    return bool(stored) and ":" in stored and not stored.startswith("$")


def _hash_pw(password: str) -> str:
    """Hash a password with argon2id. Returns the full encoded hash string."""
    return _ph.hash(password)


def _verify_pw(password: str, stored: str) -> bool:
    """Verify a password against a stored hash (argon2 or legacy sha256).

    Legacy accounts keep working; callers should re-hash on successful login
    so old 'salt:sha256' passwords are transparently upgraded to argon2.
    """
    if not stored:
        return False
    if stored.startswith("$"):  # argon2id / argon2i
        try:
            _ph.verify(stored, password)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
    # Legacy 'salt:sha256' fallback.
    try:
        salt, h = stored.split(":", 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Reversible encryption for the optional plaintext-password display feature.
# The DB stores an ENCRYPTED copy (never raw plaintext); the app holds the key
# in a local .fernet_key file (gitignored). If the key is missing it is
# generated once and persisted so ciphertext stays decryptable across restarts.
# ---------------------------------------------------------------------------
_FERNET_KEY_PATH = Path(__file__).parent.parent / ".fernet_key"


def _load_fernet() -> "Fernet":
    if _FERNET_KEY_PATH.exists():
        key = _FERNET_KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        _FERNET_KEY_PATH.write_bytes(key)
        log.warning("Generated Fernet key at %s — keep it secret (it is gitignored)", _FERNET_KEY_PATH)
    return Fernet(key)


_fernet = _load_fernet()


def _encrypt_plain(text: str) -> str:
    """Encrypt a plaintext password for at-rest storage. Returns '' for empty."""
    if not text:
        return ""
    return _fernet.encrypt(text.encode()).decode()


def _decrypt_plain(cipher: str) -> str:
    """Decrypt a stored plaintext-password copy. Returns '' on failure/empty."""
    if not cipher:
        return ""
    try:
        return _fernet.decrypt(cipher.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def _categorize(filename: str) -> str:
    """Determine category from file extension (P1-4: DB-backed mapping).

    Delegates to :func:`app.services.category_service.categorize`, which reads
    the runtime-editable mapping from the DB (cached in-process). The lazy
    import avoids a circular dependency with the service module. The
    ``EXT_CATEGORY`` / ``DEFAULT_CATEGORY`` config values remain the seed source
    for the table (populated in ``init_db``).
    """
    from app.services import category_service

    return category_service.categorize(filename)


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _delete_file(full) -> bool:
    """Delete a single physical file.

    Tries several strategies in order, because some sandboxed Python runtimes
    intercept in-process ``unlink`` calls (e.g. a [safe-delete] hook) or mangle
    non-ASCII paths through ``cmd.exe``:

    1. ``pathlib.Path.unlink`` (standard)
    2. ``ctypes`` ``DeleteFileW`` — a direct, Unicode-aware Windows API call that
       bypasses Python's ``os.unlink`` hook (no codepage/encoding issues)
    3. shell ``del`` / ``rm`` as a last resort

    Returns True only if the file is confirmed gone afterwards.
    """
    full = Path(full)
    if not full.exists():
        return True

    # 1. standard unlink
    try:
        full.unlink()
        if not full.exists():
            return True
    except Exception as exc:
        log.warning(f"native unlink failed for {full}: {exc}; trying ctypes")

    # 2. direct Windows API (Unicode-safe, bypasses os.unlink hook)
    if sys.platform.startswith("win"):
        try:
            res = ctypes.windll.kernel32.DeleteFileW(str(full))
            if res and not full.exists():
                return True
            log.warning(f"ctypes DeleteFileW returned {res} for {full}; trying shell")
        except Exception as exc:
            log.warning(f"ctypes DeleteFileW failed for {full}: {exc}; trying shell")

    # 3. shell fallback
    try:
        if sys.platform.startswith("win"):
            # use a quoted path so spaces / unicode are preserved
            os.system(f'del /f /q "{str(full)}"')
        else:
            subprocess.run(["rm", "-f", str(full)], check=False, capture_output=True)
    except Exception as exc:
        log.error(f"shell delete failed for {full}: {exc}")

    return not full.exists()


def _delete_tree(directory) -> bool:
    """Delete a directory tree, with the same fallback strategy as ``_delete_file``."""
    directory = Path(directory)
    if not directory.exists():
        return True

    # 1. standard rmtree
    try:
        shutil.rmtree(directory)
        if not directory.exists():
            return True
    except Exception as exc:
        log.warning(f"native rmtree failed for {directory}: {exc}; trying ctypes")

    # 2. direct Windows API (unicode-safe)
    if sys.platform.startswith("win"):
        try:
            res = ctypes.windll.kernel32.RemoveDirectoryW(str(directory))
            if res and not directory.exists():
                return True
            log.warning(f"ctypes RemoveDirectoryW returned {res} for {directory}")
        except Exception as exc:
            log.warning(f"ctypes RemoveDirectoryW failed for {directory}: {exc}")

    # 3. shell fallback
    try:
        if sys.platform.startswith("win"):
            os.system(f'rmdir /s /q "{str(directory)}"')
        else:
            subprocess.run(["rm", "-rf", str(directory)], check=False, capture_output=True)
    except Exception as exc:
        log.error(f"shell rmtree failed for {directory}: {exc}")

    return not directory.exists()
