# -*- coding: utf-8 -*-
"""File Server configuration — loads from .env with sensible defaults."""

import os
from pathlib import Path

# Auto-load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv is optional

# ---------- Paths ----------
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = Path(__file__).parent.parent / "server.db"
DEFAULT_CATEGORY = "其他"

# ---------- Server ----------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ---------- Admin defaults ----------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_NICKNAME = os.getenv("ADMIN_NICKNAME", "管理员")

# ---------- Upload limits ----------
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS: set[str] = set(
    e.strip().lower() for e in os.getenv("ALLOWED_EXTENSIONS", "").split(",") if e.strip()
)
BLOCKED_EXTENSIONS: set[str] = set(
    e.strip().lower() for e in os.getenv("BLOCKED_EXTENSIONS", "").split(",") if e.strip()
)

# ---------- Extension -> category mapping (70+ extensions -> 8 categories) ----------
EXT_CATEGORY: dict[str, str] = {
    ".jpg": "图片", ".jpeg": "图片", ".png": "图片", ".gif": "图片",
    ".bmp": "图片", ".webp": "图片", ".svg": "图片", ".ico": "图片",
    ".tiff": "图片", ".tif": "图片", ".heic": "图片", ".heif": "图片",
    ".pdf": "文档", ".doc": "文档", ".docx": "文档", ".xls": "文档",
    ".xlsx": "文档", ".ppt": "文档", ".pptx": "文档", ".txt": "文档",
    ".md": "文档", ".csv": "文档", ".json": "文档", ".xml": "文档",
    ".yaml": "文档", ".yml": "文档", ".log": "文档",
    ".mp4": "视频", ".avi": "视频", ".mkv": "视频", ".mov": "视频",
    ".wmv": "视频", ".flv": "视频", ".webm": "视频", ".m4v": "视频",
    ".3gp": "视频", ".ts": "视频",
    ".mp3": "音频", ".wav": "音频", ".flac": "音频", ".aac": "音频",
    ".ogg": "音频", ".wma": "音频", ".m4a": "音频", ".opus": "音频",
    ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包", ".tar": "压缩包",
    ".gz": "压缩包", ".bz2": "压缩包", ".xz": "压缩包", ".tgz": "压缩包",
    ".py": "代码", ".java": "代码", ".kt": "代码", ".js": "代码",
    ".html": "代码", ".css": "代码",
    ".apk": "安装包", ".exe": "安装包", ".msi": "安装包",
    ".dmg": "安装包", ".deb": "安装包", ".rpm": "安装包",
    ".iso": "安装包", ".img": "安装包", ".bat": "安装包",
    ".sh": "安装包", ".ps1": "安装包",
}
