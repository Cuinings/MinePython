# -*- coding: utf-8 -*-
"""Utility functions: password hashing, file categorization, size formatting."""

import hashlib
import secrets

from app.config import DEFAULT_CATEGORY, EXT_CATEGORY


def _hash_pw(password: str) -> str:
    """Hash password with random salt using SHA-256. Returns 'salt:hash'."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def _verify_pw(password: str, stored: str) -> bool:
    """Verify a password against a stored 'salt:hash' string."""
    salt, h = stored.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def _categorize(filename: str) -> str:
    """Determine category from file extension. Returns category name."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    return EXT_CATEGORY.get(f".{ext.lower()}", DEFAULT_CATEGORY)


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
