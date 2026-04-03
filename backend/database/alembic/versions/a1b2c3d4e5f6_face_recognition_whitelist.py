"""face_recognition_whitelist

Switch approved_persons from clothing-color histogram (96-float) to ArcFace
face embeddings (512-float).  Existing clothing-based rows are cleared because
their descriptors are incompatible with the new cosine-similarity matching.

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear old clothing-histogram descriptors — incompatible with ArcFace embeddings
    op.execute("DELETE FROM approved_persons")

    # Track which embedding model was used for each enrollment
    op.add_column(
        "approved_persons",
        sa.Column(
            "embedding_model",
            sa.String(length=50),
            nullable=True,
            server_default="arcface_buffalo_s",
        ),
    )


def downgrade() -> None:
    op.drop_column("approved_persons", "embedding_model")
