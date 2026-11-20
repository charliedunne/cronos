"""Modules and requirements tables plus the req_no sequence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed attribute value sets (spec: requirement-store).
STATUSES = ("draft", "in-review", "approved", "deprecated")
PRIORITIES = ("low", "medium", "high")


def upgrade() -> None:
    """Create the modules and requirements tables."""
    op.create_table(
        "modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_modules_name"),
    )

    # Requirement numbers come from a dedicated sequence that only advances,
    # so deleted identifiers are never reused (design.md decision D4).
    op.execute("CREATE SEQUENCE requirement_req_no_seq")

    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "module_id",
            sa.Integer(),
            sa.ForeignKey("modules.id"),
            nullable=False,
        ),
        sa.Column(
            "req_no",
            sa.BigInteger(),
            server_default=sa.text("nextval('requirement_req_no_seq')"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default=sa.text("'medium'"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("req_no", name="uq_requirements_req_no"),
        sa.CheckConstraint(
            "length(trim(title)) > 0", name="ck_requirements_title_nonempty"
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
            name="ck_requirements_status",
        ),
        sa.CheckConstraint(
            "priority IN (" + ", ".join(f"'{p}'" for p in PRIORITIES) + ")",
            name="ck_requirements_priority",
        ),
    )
    op.create_index("ix_requirements_module_id", "requirements", ["module_id"])


def downgrade() -> None:
    """Drop the requirements and modules tables."""
    op.drop_index("ix_requirements_module_id", table_name="requirements")
    op.drop_table("requirements")
    op.execute("DROP SEQUENCE requirement_req_no_seq")
    op.drop_table("modules")
