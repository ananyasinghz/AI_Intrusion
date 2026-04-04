"""add_snapshot_path_full

Revision ID: c1a2b3c4d5e6
Revises: ab46a5b786f1
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("snapshot_path_full", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "snapshot_path_full")
