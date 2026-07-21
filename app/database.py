# -*- coding: utf-8 -*-
"""SQLite database connection and initialization."""

import sqlite3

from app.config import DB_PATH, UPLOAD_DIR, EXT_CATEGORY


def get_db() -> sqlite3.Connection:
    """Get a new database connection with row_factory set to sqlite3.Row."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    """Initialize database tables, migrate schema, and create default admin."""
    db = get_db()

    # ---------- users table ----------
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            nickname  TEXT NOT NULL DEFAULT '',
            token     TEXT UNIQUE,
            role      TEXT NOT NULL DEFAULT 'user',
            status    TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ---------- files table ----------
    db.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            category    TEXT NOT NULL,
            filepath    TEXT NOT NULL,
            size        INTEGER NOT NULL DEFAULT 0,
            uploaded_by TEXT DEFAULT 'anonymous',
            uploaded_ip TEXT DEFAULT '',
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # Migration: add role/status/nickname columns if upgrading from v4.0
    for col, default in [("role", "'user'"), ("status", "'active'"), ("nickname", "''")]:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
        except sqlite3.OperationalError:
            pass
    # Fill empty nicknames with username for existing users
    db.execute("UPDATE users SET nickname = username WHERE nickname = '' OR nickname IS NULL")

    # Ensure upload category dirs exist
    for cat in set(EXT_CATEGORY.values()):
        (UPLOAD_DIR / cat).mkdir(exist_ok=True)
    (UPLOAD_DIR / "其他").mkdir(exist_ok=True)

    # Ensure default admin exists
    from app.utils import _hash_pw
    from app.config import ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_NICKNAME
    existing = db.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username, password, nickname, role, status) VALUES (?,?,?,?,?)",
            (ADMIN_USERNAME, _hash_pw(ADMIN_PASSWORD), ADMIN_NICKNAME, "admin", "active"),
        )

    db.commit()
    db.close()
