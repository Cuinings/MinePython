# -*- coding: utf-8 -*-
"""用户模块配置 — 加载自 .env，提供合理默认值。

这是整个项目的唯一配置来源（单一事实）。所有模块都从这里读取路径、
端口、安全与日志等开关。文件服务器 / 审计 / API 文档模块通过
``modules.user.config`` 复用同一份配置。
"""

import os
from pathlib import Path

# Auto-load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass  # dotenv is optional

# Fallback: parse .env manually when python-dotenv is unavailable, so that
# environment configuration (e.g. APP_DEBUG) is honored even without the
# optional dependency. Only sets variables that aren't already in the env.
def _load_env_file(path: Path):
    if not path.exists():
        return
    try:
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass

_load_env_file(Path(__file__).parent.parent.parent / ".env")

# ---------- Branding (工程名，全项目唯一事实源) ----------
# The project / site display name. Change it via the APP_NAME env var (or .env)
# to rebrand the whole app — backend service titles, API docs, and the web UI
# (page <title> + header) all read from here. No code edits needed.
APP_NAME = os.getenv("APP_NAME", "MinePython").strip() or "MinePython"


# ---------------------------------------------------------------------------
# Runtime site-name editing (admin UI -> /api/admin/site).
# set_app_name() updates the in-memory value immediately (so the public
# /api/app-info endpoint reflects it without a restart) and, if a .env file
# exists, persists it there so the change survives a restart. Deployments that
# drive branding purely via real environment variables have no .env file; in
# that case we only update the in-memory value (env vars are the source of
# truth and cannot be overwritten from inside the process).
# ---------------------------------------------------------------------------
def _write_env_key(key: str, value: str) -> bool:
    """Persist a single ``key=value`` line into the project .env.

    Replaces an existing line (matching key, non-comment) if present, otherwise
    appends. Quotes the value when it contains whitespace or shell-special
    chars so the manual parser in :func:`_load_env_file` reads it back cleanly.
    Returns ``False`` if there is no .env to write to (caller keeps the
    in-memory update only).
    """
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return False
    needs_quote = value != value.strip() or any(
        ch in value for ch in ' #"\'\\$`'
    )
    safe = value.replace('"', '\\"') if needs_quote else value
    line = f'{key}="{safe}"' if needs_quote else f"{key}={value}"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
        out, replaced = [], False
        for ln in lines:
            if ln.strip().startswith("#"):
                out.append(ln)
                continue
            if "=" in ln and ln.split("=", 1)[0].strip() == key:
                out.append(line)
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            if out and out[-1].strip():
                out.append("")
            out.append(line)
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def set_app_name(name: str) -> str:
    """Update the site display name at runtime and persist it.

    Used by the admin "site settings" UI. Raises ``ValueError`` on invalid
    input. Returns the normalized name.
    """
    global APP_NAME
    name = (name or "").strip()
    if not name:
        raise ValueError("Site name cannot be empty")
    if len(name) > 40:
        raise ValueError("Site name too long (max 40 characters)")
    APP_NAME = name
    _write_env_key("APP_NAME", name)
    return APP_NAME

# ---------- Paths ----------
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads")))
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent.parent.parent / "server.db")))
DEFAULT_CATEGORY = "其他"

# ---------- Server (combined entry) ----------
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ---------- Per-module entry ports (单进程模块包：每个模块可独立启动) ----------
# 四个模块各自独立运行时的端口；合并入口(modules/__main__.py)仍使用 PORT(8000)。
USER_MODULE_PORT = int(os.getenv("USER_MODULE_PORT", "8001"))
FILES_MODULE_PORT = int(os.getenv("FILES_MODULE_PORT", "8002"))
AUDIT_MODULE_PORT = int(os.getenv("AUDIT_MODULE_PORT", "8003"))
APIDOCS_MODULE_PORT = int(os.getenv("APIDOCS_MODULE_PORT", "8004"))

# ---------- Debug / safe-by-default ----------
# When False (production), the interactive API docs (/docs, /redoc,
# /openapi.json) are blocked and the global error handler stops leaking
# internal exception strings to clients (ARCH-1 / R3). Set APP_DEBUG=true
# only in trusted development environments.
DEBUG = os.getenv("APP_DEBUG", "false").strip().lower() in ("1", "true", "yes", "on")

# ---------- Orphan cleanup sweep (P1-6) ----------
# Background scan interval (seconds) for disk/DB orphans. 0 disables the sweep
# (the POST /api/admin/cleanup endpoint remains available on demand). When the
# sweep is enabled it REPORTS only by default; set ORPHAN_CLEANUP_AUTO=true to
# let it delete on its own (use with caution — deletions are audit-logged).
ORPHAN_CLEANUP_INTERVAL_SECONDS = int(os.getenv("ORPHAN_CLEANUP_INTERVAL_SECONDS", "0"))
ORPHAN_CLEANUP_AUTO = os.getenv("ORPHAN_CLEANUP_AUTO", "false").strip().lower() in (
    "1", "true", "yes", "on"
)

# ---------- Admin defaults ----------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_NICKNAME = os.getenv("ADMIN_NICKNAME", "管理员")

# ---------- Auth / session tokens ----------
# Each login mints an independent session token (multi-session, no overwrite)
# that expires after this many hours. 0/negative disables expiry.
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "168"))  # 7 days
# Background sweep interval (seconds) for purging expired token rows (ARCH-3).
TOKEN_CLEANUP_INTERVAL_SECONDS = int(os.getenv("TOKEN_CLEANUP_INTERVAL_SECONDS", "3600"))

# ---------- Login brute-force / rate limiting (ARCH-2) ----------
# Per-username lock: after MAX_LOGIN_FAILS consecutive failures the account is
# locked for LOGIN_LOCK_SECONDS. Per-IP throttle adds a second, IP-dimension
# guard so one host cannot spray many usernames. Both are in-memory (single
# process); front a multi-instance deployment with a shared store if needed.
MAX_LOGIN_FAILS = int(os.getenv("MAX_LOGIN_FAILS", "5"))
LOGIN_LOCK_SECONDS = int(os.getenv("LOGIN_LOCK_SECONDS", "900"))  # 15 min
LOGIN_IP_MAX_FAILS = int(os.getenv("LOGIN_IP_MAX_FAILS", "20"))
LOGIN_IP_WINDOW_SECONDS = int(os.getenv("LOGIN_IP_WINDOW_SECONDS", "300"))  # 5 min

# ---------- Logging (centralized here; logging_config imports these) ----------
LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).parent.parent.parent / "logs")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # ~10 MB
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", "5"))
LOG_FILE_NAME = os.getenv("LOG_FILE_NAME", "app.log")

# ---------- Upload limits ----------
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS: set[str] = set(
    e.strip().lower() for e in os.getenv("ALLOWED_EXTENSIONS", "").split(",") if e.strip()
)
BLOCKED_EXTENSIONS: set[str] = set(
    e.strip().lower() for e in os.getenv("BLOCKED_EXTENSIONS", "").split(",") if e.strip()
)

# ---------- Batch download limits (guard against oversized ZIP / timeout) ----------
MAX_BATCH_DOWNLOAD_FILES = int(os.getenv("MAX_BATCH_DOWNLOAD_FILES", "500"))
MAX_BATCH_DOWNLOAD_BYTES = int(
    os.getenv("MAX_BATCH_DOWNLOAD_BYTES", str(2 * 1024 * 1024 * 1024))  # 2 GB
)

# ---------- ADB (APK 一键安装到设备) ----------
# Path to the adb executable. Defaults to "adb" (resolved via PATH). Point it
# at an explicit binary when adb is not on PATH, e.g.
#   ADB_PATH=C:/android-sdk/platform-tools/adb.exe
ADB_PATH = os.getenv("ADB_PATH", "adb").strip() or "adb"
# Hard ceiling (seconds) for a single `adb install` so a stuck device can't
# hang the request forever (large APKs over a slow link can still take minutes).
ADB_TIMEOUT = int(os.getenv("ADB_TIMEOUT", "300"))

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
