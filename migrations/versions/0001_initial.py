# -*- coding: utf-8 -*-
"""initial schema (baseline)

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-07-21

This is the Alembic baseline for the File Server schema (P2-1). It mirrors the
ORM models in app/database.py exactly (users, tokens, files, audit_log, roles,
permissions, role_permissions). On an existing database, ``init_db()`` stamps
this revision as already-applied (the tables already exist via create_all), so
the migration itself is a no-op there; on a brand-new database, running
``alembic upgrade head`` (or letting init_db do it) creates every table.
"""

from collections import OrderedDict

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        # Recoverable plaintext copy (encrypted at rest) for admin "show password".
        sa.Column("password_plain", sa.String(), nullable=True),
        sa.Column("nickname", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("force_pw_change", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("token"),
    )
    # Non-unique indexes (unique columns above already have a unique index).
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_tokens_user_id", "tokens", ["user_id"], unique=False)

    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("filepath", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=False),
        sa.Column("uploaded_ip", sa.String(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_files_category", "files", ["category"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )


def downgrade() -> None:
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("audit_log")
    op.drop_index("ix_files_category", table_name="files")
    op.drop_table("files")
    op.drop_index("ix_tokens_user_id", table_name="tokens")
    op.drop_table("tokens")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
