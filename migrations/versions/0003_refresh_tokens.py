# -*- coding: utf-8 -*-
"""replace self-built `tokens` table with `refresh_tokens` (ARCH-9)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-25

ARCH-9 swaps the self-built session `tokens` table for a stateless, signature
verified access JWT plus a server-side `refresh_tokens` table. Access tokens
are never stored (the hot path verifies them by signature only). Refresh tokens
are stored as a SHA-256 *hash* of the opaque raw token (so a DB leak cannot be
replayed); deleting a row revokes a session immediately.

This migration:
  * drops the legacy `tokens` table (its rows were never the access token — the
    old model minted a random session string that is simply superseded by JWTs),
  * creates `refresh_tokens(id, user_id, token_hash, expires_at, device,
    created_at)` mirroring :class:`modules.user.database.RefreshToken`.

Downgrade reverses both steps, recreating the legacy `tokens` table (without
the SQLite-only ``datetime('now','localtime')`` server_default, so the
downgrade also runs on Postgres).
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tear down the legacy session table.
    op.drop_index("ix_tokens_user_id", table_name="tokens")
    op.drop_table("tokens")

    # New refresh-token store (hashed rows only).
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=False)


def downgrade() -> None:
    # Drop the refresh store.
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    # Recreate the legacy `tokens` table (cross-DB safe: no SQLite-only default).
    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_tokens_user_id", "tokens", ["user_id"], unique=False)
