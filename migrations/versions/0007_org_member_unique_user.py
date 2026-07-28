# -*- coding: utf-8 -*-
"""org_members: one department per user (成员唯一归属)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-27

Business rule change: a user belongs to **at most one** department
(部门→成员 一对多；成员→部门 唯一归属). The unique constraint on
``org_members`` moves from ``(department_id, user_id)`` to ``(user_id)``.

Steps (SQLite-safe via batch mode):
1. De-duplicate: if a user is currently in multiple departments, keep only
   the earliest membership row (lowest id) and drop the rest.
2. Rebuild the table constraint: drop ``uq_org_member_dept_user``, add
   ``uq_org_member_user`` on ``user_id``.
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Keep only the earliest membership per user (dedupe before tightening).
    op.execute(
        sa.text(
            "DELETE FROM org_members WHERE id NOT IN ("
            "SELECT MIN(id) FROM org_members GROUP BY user_id)"
        )
    )
    # 2. Swap the unique constraint (batch mode rebuilds the table on SQLite).
    with op.batch_alter_table("org_members") as batch:
        batch.drop_constraint("uq_org_member_dept_user", type_="unique")
        batch.create_unique_constraint("uq_org_member_user", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("org_members") as batch:
        batch.drop_constraint("uq_org_member_user", type_="unique")
        batch.create_unique_constraint(
            "uq_org_member_dept_user", ["department_id", "user_id"]
        )
