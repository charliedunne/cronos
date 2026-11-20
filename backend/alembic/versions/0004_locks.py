"""Locks table for exclusive editing (editing-locks spec).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the locks table.

    ``requirement_id`` is the primary key (design.md decision D5): at most
    one lock row exists per requirement and a concurrent second INSERT
    fails with a unique violation, which the API maps to HTTP 409. The FK
    cascades so deleting a requirement removes its lock automatically.
    """
    op.create_table(
        "locks",
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "holder_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_locks_holder_id", "locks", ["holder_id"])


def downgrade() -> None:
    """Drop the locks table."""
    op.drop_index("ix_locks_holder_id", table_name="locks")
    op.drop_table("locks")
