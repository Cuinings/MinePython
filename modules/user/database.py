# -*- coding: utf-8 -*-
"""用户模块数据库层 — SQLAlchemy 2.0 ORM。

定义引擎、会话工厂，以及全部 ORM 模型（User / RefreshToken / File /
AuditLog / ExtCategory / Role / Permission / RolePermission）和初始化与种子
逻辑。所有原始 ``sqlite3`` 访问已替换为 ORM，使 schema、迁移与 RBAC 种子数据
集中在一处。

这是整个项目的单一数据基座：文件服务器与审计模块都从这里导入自己的模型
（``File`` / ``ExtCategory`` / ``AuditLog``），因此本模块被 files / audit 依赖。

ARCH-10: 引擎由 ``DATABASE_URL`` 驱动。未设置时回退到本地 SQLite 文件；设为
``postgresql://…`` 时切换到 Postgres（psycopg3 同步驱动），使多实例可共享同一
数据库横向扩展。SQLite 专有的 WAL / StaticPool / check_same_thread 仅在使用
SQLite 时启用。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from modules.user.config import (
    ADMIN_NICKNAME,
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DATABASE_URL,
    DB_PATH,
    UPLOAD_DIR,
    EXT_CATEGORY,
)
from modules.user.utils import _hash_pw, _encrypt_plain, _decrypt_plain, _now_str

log = logging.getLogger("fileserver.db")


# ---------------------------------------------------------------------------
# Engine & session (ARCH-10: DATABASE_URL-driven; SQLite default, Postgres opt-in)
# ---------------------------------------------------------------------------
def _resolve_db_url() -> str:
    """Return the effective SQLAlchemy URL.

    Falls back to the local SQLite file when ``DATABASE_URL`` is unset (dev / CI
    / single-node). A bare ``postgres(ql)://`` URL is normalized to the psycopg3
    (v3) sync driver so the sync SQLAlchemy engine + ``Session`` layer keep
    working unchanged (approach A: sync SQLAlchemy + run_in_threadpool offload,
    not a full async rewrite).
    """
    url = (DATABASE_URL or "").strip()
    if not url:
        return f"sqlite:///{DB_PATH}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Only inject +psycopg when the caller didn't pin a driver (avoids clobbering
    # an explicit postgresql+psycopg2 / +asyncpg choice).
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DB_URL = _resolve_db_url()
IS_SQLITE = DB_URL.startswith("sqlite")

if IS_SQLITE:
    # Use a real connection pool (QueuePool) so concurrent requests get their own
    # SQLite connection instead of fighting over a single shared one. WAL
    # journaling (set per-connection below) lets many readers and one writer
    # proceed at once, and ``busy_timeout`` makes SQLite wait under contention
    # rather than raising "database is locked" — which previously caused
    # intermittent 500/401 errors when concurrent requests fired together.
    engine = create_engine(
        DB_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_wal(dbapi_conn, _record):
        """Enable WAL journaling + a generous busy timeout (SQLite only)."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
else:
    # Postgres (or any non-sqlite backend): a shared DB across instances is what
    # enables horizontal scaling (ARCH-10). pool_pre_ping recycles connections
    # dropped by the server / a proxy; pool_recycle guards against idle-timeout
    # resets. No SQLite-only connect_args / WAL here.
    engine = create_engine(
        DB_URL,
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_pre_ping=True,
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    # Recoverable copy of the password used ONLY for admin display ("show
    # plaintext"). Authentication always uses the salted hash in ``password``;
    # ``password_plain`` is never used for verification and is stripped from
    # the auth/session context dict.
    password_plain: Mapped[str | None] = mapped_column(String, nullable=True)
    nickname: Mapped[str] = mapped_column(String, nullable=False, default="")
    role: Mapped[str] = mapped_column(String, nullable=False, default="user", index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    force_pw_change: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)
    # Last login source IP (set on each successful login). Shown in the user's
    # own profile and the admin user-management list.
    last_login_ip: Mapped[str] = mapped_column(
        String, nullable=False, default="", server_default=text("''")
    )


class RefreshToken(Base):
    """Server-side refresh tokens (ARCH-9) — the ONLY auth state that persists.

    Replaces the legacy self-built ``tokens`` (SessionToken) table. Access is now
    a stateless, signature-verified JWT that never touches this table; only the
    infrequent /api/auth/refresh call reads here. We store a SHA-256 *hash* of
    the raw refresh token (never the token itself) so a DB leak cannot be
    replayed. Deleting a row (logout) or all a user's rows (password change /
    deactivate / admin update) revokes those sessions immediately.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    filepath: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[str] = mapped_column(String, nullable=False, default="anonymous")
    uploaded_ip: Mapped[str] = mapped_column(String, nullable=False, default="")
    uploaded_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, default="anonymous")
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False, default="")
    ip: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)


class Suggestion(Base):
    """User-submitted feature requests / suggestions (功能需求建议栏).

    Every authenticated user can submit (``suggest:submit``) and see their own
    rows; admins/reviewers holding ``suggest:view`` see all; admins holding
    ``suggest:manage`` may change status / delete any. Access is server-scoped
    exactly like :class:`AuditLog` (no client-side filtering of scope).
    """

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, default="anonymous", index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    admin_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)


class ExtCategory(Base):
    """Extension -> category mapping (P1-4).

    DB-backed and CRUD-managed so classification rules are configurable at
    runtime instead of hardcoded in ``modules.user.config.EXT_CATEGORY``. The
    in-process cache in :mod:`modules.files.services.category_service` is the hot
    path; this table is the source of truth and is seeded from ``EXT_CATEGORY``.
    """

    __tablename__ = "ext_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extension: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_str)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


# ---------------------------------------------------------------------------
# RBAC seed data
# ---------------------------------------------------------------------------
# Permission catalogue. Codes are checked by the @require_permission dependency.
PERMISSIONS: dict[str, str] = {
    "file:list": "浏览文件列表",
    "file:upload": "上传文件",
    "file:download": "下载文件",
    "file:delete_self": "删除本人上传的文件",
    "file:delete_any": "删除任意文件",
    "category:manage": "管理分类（删除分类 / 整理）",
    "user:read": "查看用户列表",
    "user:manage": "创建 / 修改 / 删除用户",
    "user:approve": "审批用户注册",
    "audit:view": "查看全部审计日志（管理员 / 审核员）",
    "audit:view_self": "查看本人审计记录（所有登录用户）",
    "audit:purge": "清空全部审计日志（仅管理员）",
    "file:adb_install": "通过 ADB 把 APK 安装到设备",
    "suggest:submit": "提交功能需求 / 建议（所有登录用户）",
    "suggest:view": "查看全部功能建议（管理员 / 审核员）",
    "suggest:manage": "处理功能建议：改状态 / 删除（管理员）",
}

# Role -> (description, [permissions]). Seeded on startup; kept in sync.
ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("超级管理员，拥有全部权限", list(PERMISSIONS.keys())),
    "reviewer": (
        "审核员：可审批用户、查看审计、管理本人文件",
        ["file:list", "file:upload", "file:download", "file:delete_self", "file:adb_install",
         "user:read", "user:approve", "audit:view", "audit:view_self",
         "suggest:submit", "suggest:view"],
    ),
    "uploader": (
        "上传者：可上传 / 下载 / 删除本人文件",
        ["file:list", "file:upload", "file:download", "file:delete_self", "file:adb_install", "audit:view_self",
         "suggest:submit"],
    ),
    "user": (
        "普通用户：可上传 / 下载 / 删除本人文件",
        ["file:list", "file:upload", "file:download", "file:delete_self", "file:adb_install", "audit:view_self",
         "suggest:submit"],
    ),
    "anonymous": (
        "匿名访客：仅可浏览与下载文件（只读，无需登录）",
        ["file:list", "file:download"],
    ),
}

# Runtime cache: role name -> set of permission codes.
_ROLE_PERMS: dict[str, set[str]] = {}


def get_permissions_for_role(role: str) -> set[str]:
    """Return the effective permission set for a role (cached)."""
    return _ROLE_PERMS.get(role, set())


def refresh_permissions() -> None:
    """Reload the role -> permissions cache from the database."""
    global _ROLE_PERMS
    with SessionLocal() as db:
        rows = db.execute(
            select(Role.name, Permission.code)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        ).all()
    mapping: dict[str, set[str]] = {}
    for name, code in rows:
        mapping.setdefault(name, set()).add(code)
    _ROLE_PERMS = mapping


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------
def get_db() -> Iterable[Session]:
    """FastAPI dependency that yields a session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def orm_to_dict(obj) -> dict:
    """Convert an ORM instance to a dict keyed by column names."""
    if obj is None:
        return {}
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


def audit_logs_to_dicts(db, rows) -> list[dict]:
    """Convert AuditLog rows to API dicts, attaching each operator's nickname.

    The display name prefers ``nickname`` and falls back to ``username`` when
    the account no longer exists (e.g. deleted users) or has no nickname set.
    ``username`` is retained on every row for identity, filtering and CSV export.
    """
    unames = {r.username for r in rows}
    nick_map: dict[str, str] = {}
    if unames:
        for uname, nick in db.execute(
            select(User.username, User.nickname).where(User.username.in_(unames))
        ).all():
            nick_map[uname] = (nick or "") or uname
    out = []
    for r in rows:
        d = orm_to_dict(r)
        d["nickname"] = nick_map.get(r.username, r.username)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Initialization & seeding
# ---------------------------------------------------------------------------
def _migrate_legacy_schema() -> None:
    """Add columns that may be missing on databases created before v4.1."""
    with engine.begin() as conn:
        existing = {c["name"] for c in inspect(engine).get_columns("users")}
        for col, ddl in [
            ("nickname", "TEXT NOT NULL DEFAULT ''"),
            ("role", "TEXT NOT NULL DEFAULT 'user'"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("is_default", "INTEGER NOT NULL DEFAULT 0"),
            ("force_pw_change", "INTEGER NOT NULL DEFAULT 0"),
            ("password_plain", "TEXT"),
            ("last_login_ip", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if col not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning("Migration skipped for %s: %s", col, exc)


def _seed_rbac(db: Session) -> None:
    """Idempotently create permissions & roles and wire their mappings."""
    perm_ids: dict[str, int] = {}
    for code, desc in PERMISSIONS.items():
        perm = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if perm is None:
            perm = Permission(code=code, description=desc)
            db.add(perm)
            db.flush()
        perm_ids[code] = perm.id

    for name, (desc, codes) in ROLES.items():
        role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if role is None:
            role = Role(name=name, description=desc)
            db.add(role)
            db.flush()
        # Replace mappings so the seed stays authoritative on each boot.
        db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for code in codes:
            db.add(RolePermission(role_id=role.id, permission_id=perm_ids[code]))
    db.commit()


def _ensure_alembic_baseline() -> None:
    """Bring the database under Alembic control (P2-1) — idempotent & safe.

    Alembic is now the source of truth for schema evolution. This helper makes
    adoption non-breaking for every existing database:

    * No ``alembic_version`` table yet (fresh DB OR a pre-Alembic DB):
        - first ``create_all`` guarantees the tables physically exist (a safe
          no-op when they already do), then
        - ``alembic stamp head`` marks the baseline revision as applied, so the
          current schema is treated as "already migrated". No data is touched.
    * ``alembic_version`` already present (Alembic-managed DB):
        - ``alembic upgrade head`` applies any newer migrations on top.

    If Alembic cannot be imported (e.g. a partial deploy), we silently fall
    back to ``create_all`` so the app still boots. Everything here is additive —
    nothing is ever dropped — so existing data is always preserved.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        log.warning(
            "alembic not installed; falling back to Base.metadata.create_all()"
        )
        Base.metadata.create_all(bind=engine)
        return

    root = Path(__file__).parent.parent.parent

    def _alembic_cfg() -> "Config":
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "migrations"))
        cfg.set_main_option("sqlalchemy.url", str(engine.url))
        return cfg

    has_version = False
    try:
        has_version = "alembic_version" in inspect(engine).get_table_names()
    except Exception:  # pragma: no cover - defensive
        has_version = False

    if not has_version:
        # Guarantee physical tables, then mark the baseline so future
        # `alembic upgrade head` calls are no-ops instead of re-creating tables.
        Base.metadata.create_all(bind=engine)
        try:
            command.stamp(_alembic_cfg(), "head")
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("alembic stamp head failed (non-fatal): %s", exc)
    else:
        try:
            command.upgrade(_alembic_cfg(), "head")
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "alembic upgrade head failed (non-fatal); falling back to create_all: %s",
                exc,
            )
            Base.metadata.create_all(bind=engine)


def init_db() -> None:
    """Create/evolve tables via Alembic (P2-1), then seed admin & RBAC data."""
    _ensure_alembic_baseline()
    _migrate_legacy_schema()

    # Ensure upload category directories exist
    for cat in set(EXT_CATEGORY.values()) | {"其他"}:
        (UPLOAD_DIR / cat).mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        # Default admin (idempotent). The bootstrap account is flagged
        # is_default so the UI/API can refuse to delete it (prevents lockout).
        existing = db.execute(select(User).where(User.username == ADMIN_USERNAME)).scalar_one_or_none()
        if existing is None:
            db.add(
                User(
                    username=ADMIN_USERNAME,
                    password=_hash_pw(ADMIN_PASSWORD),
                    password_plain=_encrypt_plain(ADMIN_PASSWORD),
                    nickname=ADMIN_NICKNAME,
                    role="admin",
                    status="active",
                    is_default=True,
                    force_pw_change=True,
                )
            )
        else:
            # Older databases may already contain the admin without the flag
            # or without a recoverable password copy. Backfill both.
            existing.is_default = True
            if not existing.password_plain:
                existing.password_plain = _encrypt_plain(ADMIN_PASSWORD)
            # Force a password change if the admin is still on the default one.
            if _decrypt_plain(existing.password_plain or "") == ADMIN_PASSWORD:
                existing.force_pw_change = True
        db.commit()

        _seed_rbac(db)

        # P1-4: seed the extension->category mapping from the hardcoded
        # EXT_CATEGORY defaults the first time only. After that the
        # ext_category table is the source of truth and can be edited via the
        # category-mapping CRUD API (admin, category:manage).
        if db.execute(select(ExtCategory)).first() is None:
            db.add_all(
                [ExtCategory(extension=ext, category=cat) for ext, cat in EXT_CATEGORY.items()]
            )
            db.commit()

    # P0-2: encrypt any legacy plaintext password_plain already in the DB so it
    # is never stored as raw text. Already-encrypted values decrypt fine and are
    # left untouched; only raw plaintext triggers re-encryption.
    with SessionLocal() as db:
        for u in db.execute(select(User)).scalars().all():
            p = u.password_plain
            if p and _decrypt_plain(p) == "":
                u.password_plain = _encrypt_plain(p)
        db.commit()

    refresh_permissions()
    log.info("Database initialized (RBAC roles: %s)", ", ".join(ROLES))
