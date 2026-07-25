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
    # If a bind-mounted .env is actually a directory (Docker auto-creates the
    # mount point as a dir when the host file is absent), we cannot write to it.
    if env_path.is_dir():
        return False
    # Create the file on first write so admin-UI edits persist even when no
    # .env shipped initially (otherwise the in-memory change is lost on restart).
    if not env_path.exists():
        try:
            env_path.write_text("", encoding="utf-8")
        except OSError:
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


def set_app_name(name: str) -> tuple[str, bool]:
    """Update the site display name at runtime and persist it.

    Used by the admin "site settings" UI. Raises ``ValueError`` on invalid
    input. Returns ``(normalized_name, persisted_ok)``.
    """
    global APP_NAME
    name = (name or "").strip()
    if not name:
        raise ValueError("Site name cannot be empty")
    if len(name) > 40:
        raise ValueError("Site name too long (max 40 characters)")
    APP_NAME = name
    persisted = _write_env_key("APP_NAME", name)
    return APP_NAME, persisted


# ---------------------------------------------------------------------------
# Runtime max-upload-size editing (admin UI -> /api/admin/upload-limit).
# Same pattern as set_app_name(): update the in-memory values immediately
# (so the running upload guard picks up the change without a restart) and,
# when a .env exists, persist MAX_UPLOAD_SIZE_MB so a restart keeps the
# admin's choice. file_service.py reads ``config.MAX_UPLOAD_SIZE_BYTES`` on
# every upload, so the new cap takes effect on the very next request.
# ---------------------------------------------------------------------------
def get_max_upload_size_mb() -> int:
    """Current per-file upload size cap in MB (admin-configurable)."""
    return MAX_UPLOAD_SIZE_MB


def set_max_upload_size_mb(mb) -> tuple[int, bool]:
    """Update the per-file upload cap at runtime and persist it.

    Used by the admin settings UI. Raises ``ValueError`` on invalid input.
    Returns ``(normalized_mb, persisted_ok)``.
    """
    global MAX_UPLOAD_SIZE_MB, MAX_UPLOAD_SIZE_BYTES
    try:
        mb = int(mb)
    except (TypeError, ValueError):
        raise ValueError("Upload limit must be a number (MB)")
    if mb < 1:
        raise ValueError("Upload limit must be at least 1 MB")
    if mb > 1024 * 1024:  # 1 TB ceiling guards against typos
        raise ValueError("Upload limit too large (max 1048576 MB)")
    MAX_UPLOAD_SIZE_MB = mb
    MAX_UPLOAD_SIZE_BYTES = mb * 1024 * 1024
    persisted = _write_env_key("MAX_UPLOAD_SIZE_MB", str(mb))
    return MAX_UPLOAD_SIZE_MB, persisted


# ---------------------------------------------------------------------------
# Runtime per-user quota (MB) and upload rate-limit editing (admin UI).
# Same .env-backed pattern as set_max_upload_size_mb(); both persist so a
# restart keeps the admin's choice. file_service.py reads
# ``config.MAX_USER_UPLOAD_BYTES`` / ``config.UPLOAD_RATE_LIMIT`` on every
# upload, so changes take effect on the very next request.
# ---------------------------------------------------------------------------
def get_max_user_upload_mb() -> int:
    """Current per-user total storage quota in MB (admin-configurable, 0=off)."""
    return MAX_USER_UPLOAD_BYTES // (1024 * 1024)


def set_max_user_upload_mb(mb) -> tuple[int, bool]:
    """Update the per-user quota at runtime and persist it.

    ``mb`` is in MB; 0 disables the quota. Raises ``ValueError`` on
    invalid input. Returns ``(normalized_mb, persisted_ok)``.
    """
    global MAX_USER_UPLOAD_BYTES
    try:
        mb = int(mb)
    except (TypeError, ValueError):
        raise ValueError("Quota must be a number (MB)")
    if mb < 0:
        raise ValueError("Quota cannot be negative (use 0 to disable)")
    MAX_USER_UPLOAD_BYTES = mb * 1024 * 1024
    persisted = _write_env_key("MAX_USER_UPLOAD_BYTES", str(mb))
    return mb, persisted


def get_upload_rate_limit() -> int:
    """Current uploads-per-window cap (admin-configurable, 0=off)."""
    return UPLOAD_RATE_LIMIT


def set_upload_rate_limit(n) -> tuple[int, bool]:
    """Update the upload rate limit at runtime and persist it.

    ``n`` = max uploads per UPLOAD_RATE_WINDOW_SECONDS. 0 disables the
    limiter. Raises ``ValueError`` on invalid input. Returns
    ``(value, persisted_ok)``.
    """
    global UPLOAD_RATE_LIMIT
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError("Rate limit must be a number")
    if n < 0:
        raise ValueError("Rate limit cannot be negative (use 0 to disable)")
    UPLOAD_RATE_LIMIT = n
    persisted = _write_env_key("UPLOAD_RATE_LIMIT", str(n))
    return n, persisted


# ---------- Paths ----------
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads")))
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent.parent.parent / "server.db")))
DEFAULT_CATEGORY = "其他"

# ---------- Database (ARCH-10: Postgres / horizontal scaling) ----------
# DATABASE_URL is the single switch that moves the whole app off SQLite onto a
# shared database (Postgres) so multiple instances can run behind a load
# balancer. When UNSET (the default), the app keeps using the local SQLite file
# at DB_PATH — so local dev, CI and existing single-node deployments are wholly
# unaffected. To scale out, point every instance at the same Postgres:
#     DATABASE_URL=postgresql://user:pass@db-host:5432/minepython
# A bare ``postgresql://`` / ``postgres://`` URL is normalized to the psycopg3
# (v3) sync driver in database.py; pass ``postgresql+psycopg://`` explicitly to
# be unambiguous. SQLite-only behaviour (WAL journaling, StaticPool, the
# check_same_thread arg) is auto-disabled when a non-sqlite URL is used.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


# ---------- JWT (ARCH-9: stateless access + refresh tokens) ----------
# The hot path (every authenticated request) verifies a short-lived access JWT
# by SIGNATURE ONLY — no database round-trip — which is what makes the service
# stateless and horizontally scalable. Refresh tokens are the ONLY server-side
# state (hashed rows in the ``refresh_tokens`` table) and are consulted only on
# the infrequent /api/auth/refresh call, so logout / password-change can still
# revoke sessions immediately.
#
# JWT_SECRET MUST be identical on every instance (they all verify each other's
# tokens). Set it explicitly in production. When unset we load — or generate
# once and persist — a local ``.jwt_secret`` file so single-node dev/CI just
# works and tokens survive a restart. A generated key is NOT shared across
# hosts, so a multi-instance deployment must set JWT_SECRET via the environment.
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "minepython").strip() or "minepython"
# Access token lifetime (minutes). Keep this short — it cannot be revoked before
# it expires (that's the trade-off for statelessness).
JWT_ACCESS_TTL_MINUTES = int(os.getenv("JWT_ACCESS_TTL_MINUTES", "30"))
# Refresh token lifetime (days). This is the effective "stay logged in" window.
JWT_REFRESH_TTL_DAYS = int(os.getenv("JWT_REFRESH_TTL_DAYS", "7"))

_JWT_SECRET_PATH = Path(__file__).parent.parent.parent / ".jwt_secret"


def _load_jwt_secret() -> str:
    """Resolve the HMAC signing secret for JWTs (env > file > generate).

    Precedence:
    1. ``JWT_SECRET`` env var — the ONLY correct option for multi-instance
       deployments (all nodes must share it).
    2. A persisted ``.jwt_secret`` file next to the project root — auto-created
       on first run so single-node dev/CI works and tokens survive restarts.
    """
    env_secret = os.getenv("JWT_SECRET", "").strip()
    if env_secret:
        return env_secret
    try:
        if _JWT_SECRET_PATH.exists():
            existing = _JWT_SECRET_PATH.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        import secrets as _secrets
        generated = _secrets.token_hex(32)
        _JWT_SECRET_PATH.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        # Last-resort ephemeral secret (tokens won't survive a restart). Only
        # hit when the filesystem is read-only; env var is the fix.
        import secrets as _secrets
        return _secrets.token_hex(32)


JWT_SECRET = _load_jwt_secret()

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
# When False (production), the global error handler stops leaking internal
# exception strings to clients (ARCH-1 / R3). Set APP_DEBUG=true only in
# trusted development environments.
#
# NOTE: whether the interactive API docs (/docs, /redoc, /openapi.json) are
# exposed is controlled by API_DOCS_ENABLED below — deliberately DECOUPLED
# from DEBUG, so you can keep DEBUG=false (no exception leakage) while still
# serving the docs by setting API_DOCS_ENABLED=true.
DEBUG = os.getenv("APP_DEBUG", "false").strip().lower() in ("1", "true", "yes", "on")

# ---------- API docs exposure (independent of DEBUG) ----------
# Decouples "expose interactive API docs" from "leak exceptions" (DEBUG).
# Defaults to following DEBUG (safe-by-default: docs hidden when DEBUG=false),
# but can be forced on with API_DOCS_ENABLED=true even in production/non-DEBUG
# deployments that still want the Swagger/ReDoc portals reachable.
_api_docs_env = os.getenv("API_DOCS_ENABLED", "").strip().lower()
API_DOCS_ENABLED = (
    _api_docs_env in ("1", "true", "yes", "on") if _api_docs_env else DEBUG
)

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

# ---------- Auth / session tokens (ARCH-9 / ARCH-10) ----------
# Access tokens are stateless JWTs (verified by signature, no DB). Refresh
# tokens are opaque strings whose SHA-256 hash lives in the ``refresh_tokens``
# table; the sweep below deletes expired rows so the table stays small.
# 0 disables the sweep.
REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS = int(os.getenv("REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS", "3600"))
# Audit-log retention: rows older than this many days are purged by a
# background sweep. 0 disables retention (keep everything forever).
AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
# Permission cache (in-memory ``_ROLE_PERMS``) is reloaded from the DB on this
# interval so role/permission changes propagate across instances (ARCH-10). 0
# disables the periodic reload (reload only at startup).
PERMISSION_CACHE_REFRESH_SECONDS = int(os.getenv("PERMISSION_CACHE_REFRESH_SECONDS", "300"))
# Shared store for the upload rate limiter so it works across instances
# (ARCH-10). Set to a Redis URL (e.g. ``redis://host:6379/0``) to enable;
# empty = in-memory single-process limiter (the default for single instances).
RATE_LIMIT_STORE = os.getenv("RATE_LIMIT_STORE", "").strip()
# When true, the refresh token is issued as an httpOnly + SameSite cookie
# (instead of returned in the JSON body), shrinking the XSS blast radius.
# The access token stays in localStorage. Defaults to off so local http dev
# keeps working; enable behind HTTPS in production.
REFRESH_TOKEN_IN_COOKIE = os.getenv("REFRESH_TOKEN_IN_COOKIE", "false").strip().lower() in (
    "1", "true", "yes", "on"
)

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
# Default blocklist of server-side script types that have no legitimate use in a
# file store and are classic upload-RCE vectors if the uploads dir is ever served
# by a web server. Note: .apk/.exe/.sh/.bat/.html/.svg/.js/.py are intentionally
# NOT blocked -- they are first-class content here and are neutralized instead by
# the no-inline / nosniff handling on preview & download (see modules.files.files).
BLOCKED_EXTENSIONS: set[str] = set(
    e.strip().lower() for e in os.getenv(
        "BLOCKED_EXTENSIONS",
        ".php,.phtml,.php3,.php4,.php5,.asp,.aspx,.jsp,.jspx,.cgi,.pl",
    ).split(",") if e.strip()
)

# ---------- Upload rate limiting & per-user quota (P5, default OFF) ----------
# In-memory, single-process. Set UPLOAD_RATE_LIMIT > 0 to cap how many uploads
# a user may start per UPLOAD_RATE_WINDOW_SECONDS. 0 disables the limiter.
UPLOAD_RATE_LIMIT = int(os.getenv("UPLOAD_RATE_LIMIT", "0"))
UPLOAD_RATE_WINDOW_SECONDS = int(os.getenv("UPLOAD_RATE_WINDOW_SECONDS", "60"))
# Per-user total stored size in bytes. 0 (default) disables the quota check.
MAX_USER_UPLOAD_BYTES = int(os.getenv("MAX_USER_UPLOAD_BYTES", "0")) * 1024 * 1024

# ---------- Batch upload caps (P6) ----------
# Guard against a single request that would flush hundreds of GB to disk before
# the one-shot commit. Count cap + total-size cap (reuses the 2 GB download cap).
MAX_BATCH_UPLOAD_FILES = int(os.getenv("MAX_BATCH_UPLOAD_FILES", "100"))

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
