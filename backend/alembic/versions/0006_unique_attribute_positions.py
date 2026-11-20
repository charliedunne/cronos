"""Enforce unique attribute positions per work-item type (work-items spec).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20

Before this revision the ``position`` column only carried display order and
could repeat. The spec now requires positions to be unique within a type, so
any type whose attributes share a position is first renumbered to a dense
0..n-1 sequence in its current display order (position, then id), preserving
the relative order of its attributes. The ``(type_id, position)`` unique
constraint is then added as an integrity backstop; the API performs the same
check up front to return a clear 409 message.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Renumber duplicate positions per type, then add the unique constraint."""
    op.execute(
        """
        WITH dup_types AS (
            SELECT type_id
            FROM attribute_definitions
            GROUP BY type_id
            HAVING COUNT(*) > COUNT(DISTINCT position)
        )
        UPDATE attribute_definitions ad
        SET position = n.ord
        FROM (
            SELECT a.id,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.type_id
                       ORDER BY a.position, a.id
                   ) - 1 AS ord
            FROM attribute_definitions a
            JOIN dup_types d ON d.type_id = a.type_id
        ) n
        WHERE ad.id = n.id
        """
    )
    op.create_unique_constraint(
        "uq_attribute_definitions_type_position",
        "attribute_definitions",
        ["type_id", "position"],
    )


def downgrade() -> None:
    """Drop the unique constraint (positions may repeat again)."""
    op.drop_constraint(
        "uq_attribute_definitions_type_position",
        "attribute_definitions",
        type_="unique",
    )
