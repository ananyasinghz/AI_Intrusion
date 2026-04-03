"""add_approved_persons

Revision ID: e7f8a9b0c1d2
Revises: ab46a5b786f1
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "ab46a5b786f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approved_persons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("descriptor", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(), nullable=True),
        sa.Column("enrolled_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["enrolled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approved_persons_id"), "approved_persons", ["id"], unique=False)

    op.add_column("incidents", sa.Column("is_approved", sa.Boolean(), nullable=True))
    op.execute("UPDATE incidents SET is_approved = 0 WHERE is_approved IS NULL")


def downgrade() -> None:
    op.drop_column("incidents", "is_approved")
    op.drop_index(op.f("ix_approved_persons_id"), table_name="approved_persons")
    op.drop_table("approved_persons")
