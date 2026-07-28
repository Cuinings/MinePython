# -*- coding: utf-8 -*-
"""add org_departments + org_members tables (组织架构)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-27

Two tables backing the organization-structure module (组织架构):
``org_departments`` (self-referencing department tree) and ``org_members``
(user ↔ department assignments with a title). Mirrors the ORM models in
``modules.user.database``. On a fresh database the tables are also created by
``Base.metadata.create_all()``; this migration keeps existing Alembic-managed
databases in sync on ``alembic upgrade head``.
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_departments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("org_departments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_departments_parent_id", "org_departments", ["parent_id"], unique=False)

    op.create_table(
        "org_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "department_id",
            sa.Integer(),
            sa.ForeignKey("org_departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("(datetime('now','localtime'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("department_id", "user_id", name="uq_org_member_dept_user"),
    )
    op.create_index("ix_org_members_department_id", "org_members", ["department_id"], unique=False)
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_org_members_user_id", table_name="org_members")
    op.drop_index("ix_org_members_department_id", table_name="org_members")
    op.drop_table("org_members")
    op.drop_index("ix_org_departments_parent_id", table_name="org_departments")
    op.drop_table("org_departments")
