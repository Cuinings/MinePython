# -*- coding: utf-8 -*-
"""add suggestions table (功能需求建议栏)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-26

New table backing the suggestion board (功能需求建议栏). Mirrors the
Suggestion ORM model in modules/user/database.py. On a fresh database the
table is also created by Base.metadata.create_all(); this migration keeps
existing Alembic-managed databases in sync on `alembic upgrade head`.
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(16), nullable=False, server_default=sa.text("'other'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("admin_note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.Column(
            "updated_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_suggestions_username", "suggestions", ["username"], unique=False)
    op.create_index("ix_suggestions_status", "suggestions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_suggestions_status", table_name="suggestions")
    op.drop_index("ix_suggestions_username", table_name="suggestions")
    op.drop_table("suggestions")
