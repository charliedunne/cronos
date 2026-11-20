"""Generalize requirements into typed work items (work-items spec).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20

Creates the type registry (``work_item_types``, ``attribute_definitions``),
seeds the built-in "requirement" type, renames ``requirements`` to
``work_items`` adding ``type_id`` and the JSONB ``attributes`` column, moves
each existing requirement's text/status/priority into its attributes map,
and retargets the ``locks`` foreign key (the table rename carries it).
Existing ``req_no`` values and identifiers are preserved (design.md D1/D5).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Built-in requirement type attribute value sets (spec: work-items).
STATUSES = ("draft", "in-review", "approved", "deprecated")
PRIORITIES = ("low", "medium", "high")


def upgrade() -> None:
    """Create the type registry and generalize requirements to work items."""
    op.create_table(
        "work_item_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("id_prefix", sa.String(length=16), nullable=False),
        sa.Column(
            "is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_work_item_types_name"),
    )

    op.create_table(
        "attribute_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "type_id",
            sa.Integer(),
            sa.ForeignKey("work_item_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "required", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "default_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "position",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "type_id", "key", name="uq_attribute_definitions_type_key"
        ),
    )
    op.create_index(
        "ix_attribute_definitions_type_id", "attribute_definitions", ["type_id"]
    )

    # Seed the built-in requirement type (id = 1) with its attribute set.
    op.execute(
        "INSERT INTO work_item_types (id, name, description, id_prefix, is_builtin) "
        "VALUES (1, 'requirement', 'Built-in requirement type', 'REQ', TRUE)"
    )
    status_options = ", ".join(f"'{s}'" for s in STATUSES)
    priority_options = ", ".join(f"'{p}'" for p in PRIORITIES)
    op.execute(
        "INSERT INTO attribute_definitions "
        "(type_id, key, label, data_type, options, required, default_value, position) "
        "VALUES "
        "(1, 'text', 'Text', 'text', NULL, FALSE, to_jsonb(''::text), 1), "
        f"(1, 'status', 'Status', 'enum', to_jsonb(ARRAY[{status_options}]::text[]), "
        "FALSE, to_jsonb('draft'::text), 2), "
        f"(1, 'priority', 'Priority', 'enum', to_jsonb(ARRAY[{priority_options}]::text[]), "
        "FALSE, to_jsonb('medium'::text), 3)"
    )

    # Rename the element table; the locks foreign key follows the rename.
    op.rename_table("requirements", "work_items")

    # Every existing row becomes a work item of the built-in type.
    op.add_column(
        "work_items",
        sa.Column(
            "type_id",
            sa.Integer(),
            sa.ForeignKey("work_item_types.id"),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_index("ix_work_items_type_id", "work_items", ["type_id"])
    op.alter_column("work_items", "type_id", server_default=None)

    # Move the fixed attribute values into the JSONB attributes map.
    op.add_column(
        "work_items",
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        "UPDATE work_items SET attributes = jsonb_build_object("
        "'text', \"text\", 'status', status, 'priority', priority)"
    )

    # Drop the now-redundant fixed columns and their check constraints.
    op.drop_constraint("ck_requirements_status", table_name="work_items")
    op.drop_constraint("ck_requirements_priority", table_name="work_items")
    op.drop_column("work_items", "text")
    op.drop_column("work_items", "status")
    op.drop_column("work_items", "priority")

    # Rename the module index and add the title index (design.md D2).
    op.execute("ALTER INDEX ix_requirements_module_id RENAME TO ix_work_items_module_id")
    op.create_index("ix_work_items_title", "work_items", ["title"])

    # The lock's primary key column is retargeted by the table rename;
    # rename it to match the generalized model.
    op.alter_column("locks", "requirement_id", new_column_name="item_id")


def downgrade() -> None:
    """Restore the requirements schema.

    Work items of non-built-in types and their attribute values cannot be
    represented in the old schema and are lost on downgrade (design.md risk
    note: reversible where practical).
    """
    op.alter_column("locks", "item_id", new_column_name="requirement_id")
    op.drop_index("ix_work_items_title", table_name="work_items")
    op.execute(
        "ALTER INDEX ix_work_items_module_id RENAME TO ix_requirements_module_id"
    )

    # Restore the fixed columns from the attributes map (built-in values).
    op.add_column(
        "work_items",
        sa.Column(
            "text", sa.Text(), server_default=sa.text("''"), nullable=False
        ),
    )
    op.add_column(
        "work_items",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
    )
    op.add_column(
        "work_items",
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default=sa.text("'medium'"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE work_items SET "
        "text = COALESCE(attributes->>'text', ''), "
        "status = COALESCE(attributes->>'status', 'draft'), "
        "priority = COALESCE(attributes->>'priority', 'medium')"
    )

    op.drop_column("work_items", "attributes")
    op.drop_index("ix_work_items_type_id", table_name="work_items")
    op.drop_column("work_items", "type_id")

    op.rename_table("work_items", "requirements")
    op.create_check_constraint(
        "ck_requirements_status",
        "requirements",
        "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
    )
    op.create_check_constraint(
        "ck_requirements_priority",
        "requirements",
        "priority IN (" + ", ".join(f"'{p}'" for p in PRIORITIES) + ")",
    )

    op.drop_table("attribute_definitions")
    op.execute("DELETE FROM work_item_types WHERE id = 1")
    op.drop_table("work_item_types")
