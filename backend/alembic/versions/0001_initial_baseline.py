"""Initial baseline schema.

Revision ID: 0001
Revises:
Create Date: 2026-11-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the initial baseline (no tables yet)."""
    pass


def downgrade() -> None:
    """Revert the initial baseline."""
    pass
