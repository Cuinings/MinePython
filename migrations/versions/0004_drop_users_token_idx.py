# -*- coding: utf-8 -*-
"""drop legacy `users.token` column + index `refresh_tokens.expires_at` (cleanup)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-25

Housekeeping after ARCH-9/10:
  * `users.token` — a leftover column from the pre-JWT session model. Nothing
    reads or writes it anymore (access is a stateless JWT, refresh lives in
    `refresh_tokens`), so it is dropped. SQLite refuses to DROP COLUMN on a
    UNIQUE column until its unique index is removed first, so we drop the index
    ahead of the column (idempotent — guarded so a re-run is a no-op).
  * `refresh_tokens.expires_at` — the expired-row sweep (`purge_expired_tokens`)
    filters on this column; an index keeps the sweep cheap as the table grows.
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Drop the unique index that sits on the legacy column first — SQLite
    #    cannot DROP COLUMN a UNIQUE column while its index exists.
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users'")
    )}
    if "ix_users_token" in existing:
        op.drop_index("ix_users_token", table_name="users")

    # 2) Drop the dead column (idempotent: ignore "no such column").
    try:
        op.drop_column("users", "token")
    except Exception:
        pass

    # 3) Speed up the expired refresh-token sweep.
    if "ix_refresh_tokens_expires_at" not in existing:
        op.create_index(
            "ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False
        )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.add_column("users", sa.Column("token", sa.String(), nullable=True))
    op.create_index("ix_users_token", "users", ["token"], unique=True)
