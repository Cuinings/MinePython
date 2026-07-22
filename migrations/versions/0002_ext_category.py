# -*- coding: utf-8 -*-
"""add ext_category mapping table (P1-4)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21

P1-4 moves the extension -> category classification rules out of the hardcoded
app.config.EXT_CATEGORY dict and into a DB table so they can be managed at
runtime via the category-mapping CRUD API. init_db() seeds the rows from the
old dict on first boot; this migration just creates the table.
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ext_category",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("extension", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extension"),
    )
    op.create_index("ix_ext_category_extension", "ext_category", ["extension"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ext_category_extension", table_name="ext_category")
    op.drop_table("ext_category")
