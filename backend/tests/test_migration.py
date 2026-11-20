"""Round-trip test for the 0005 work-items migration (task 5.3).

The pre-migration schema is rebuilt on a throwaway scratch database by
applying revisions 0001-0004 programmatically (the alembic env.py hardcodes
the application's database URL, so the revision modules are driven directly
through :class:`MigrationContext`/:class:`Operations`). Old-style requirement
rows — including one relying on column server defaults and one carrying a
lock — are seeded, revision 0005 is applied, and every preservation rule of
the work-items spec is asserted: rows become built-in-type work items with
their text/status/priority moved into the JSONB attributes map, req_no (and
therefore the rendered identifier) is unchanged, and the lock's foreign key
is retargeted to ``work_items.id``.

The scratch database is created and dropped by the local superuser over the
Unix socket; when that is unavailable the test skips itself.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

#: Directory holding the alembic revision modules.
VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: Superuser access over the local Unix socket (peer auth), maintenance DB.
ADMIN_URL = "postgresql+psycopg://cavt@/postgres?host=/home/cavt/.cronos/pgsock"

#: Template for scratch-database URLs, keyed by database name.
SCRATCH_URL_TEMPLATE = "postgresql+psycopg://cavt@/{db}?host=/home/cavt/.cronos/pgsock"


def _load_revision(filename: str):
    """Load an alembic revision module from the versions directory.

    Revision file names start with a digit and are not importable by name,
    so they are loaded explicitly from their path.

    @param filename The revision file name (e.g. ``0005_work_items.py``).
    @return The loaded module exposing ``upgrade()`` / ``downgrade()``.
    """
    path = VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"rev_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_revision(engine, revision_module) -> None:
    """Run one revision's ``upgrade()`` against the engine atomically.

    @param engine The SQLAlchemy engine bound to the scratch database.
    @param revision_module The loaded revision module to apply.
    """
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            revision_module.upgrade()


def _admin_engine():
    """Create an autocommit engine for CREATE/DROP DATABASE statements."""
    return create_engine(ADMIN_URL, execution_options={"isolation_level": "AUTOCOMMIT"})


def test_0005_migration_preserves_requirements():
    """Migrating a populated pre-work-items schema preserves all data.

    The scratch database is entirely self-contained; JSONB values are read
    back already decoded by the driver (dicts and plain strings).
    """
    db_name = f"cronos_mig_{uuid.uuid4().hex[:12]}"
    try:
        admin_engine = _admin_engine()
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        admin_engine.dispose()
    except OperationalError as exc:
        pytest.skip(f"scratch database unavailable: {exc}")

    try:
        engine = create_engine(SCRATCH_URL_TEMPLATE.format(db=db_name))
        try:
            # --- Build the pre-migration schema (revisions 0001-0004) --
            for filename in (
                "0001_initial_baseline.py",
                "0002_users_sessions.py",
                "0003_modules_requirements.py",
                "0004_locks.py",
            ):
                _apply_revision(engine, _load_revision(filename))

            # --- Seed old-style data -----------------------------------
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, username, password_hash) "
                        "VALUES (1, 'migrator', 'x')"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO modules (id, name, created_by) "
                        "VALUES (1, 'legacy module', 1)"
                    )
                )
                # Explicit attribute values...
                conn.execute(
                    text(
                        "INSERT INTO requirements "
                        "(id, module_id, req_no, title, text, status, priority, created_by) "
                        "VALUES (1, 1, 10, 'legacy one', 'first body', 'approved', 'high', 1)"
                    )
                )
                # ...and one relying on the column server defaults.
                conn.execute(
                    text(
                        "INSERT INTO requirements "
                        "(id, module_id, req_no, title, created_by) "
                        "VALUES (2, 1, 11, 'legacy two', 1)"
                    )
                )
                # A lock on the first requirement (old column name).
                conn.execute(
                    text("INSERT INTO locks (requirement_id, holder_id) VALUES (1, 1)")
                )

            # --- Apply the migration under test ------------------------
            _apply_revision(engine, _load_revision("0005_work_items.py"))

            # --- Assert: rows became built-in-type work items ----------
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, type_id, req_no, title, attributes "
                        "FROM work_items ORDER BY id"
                    )
                ).all()

            assert [r[0] for r in rows] == [1, 2]
            first, second = rows
            # Every existing row is a work item of the built-in type.
            assert first[1] == 1 and second[1] == 1
            # req_no (and thus the rendered identifier) is preserved:
            # REQ-000010 / REQ-000011, exactly as before the migration.
            assert (first[2], second[2]) == (10, 11)
            assert (first[3], second[3]) == ("legacy one", "legacy two")
            # text/status/priority moved into the JSONB attributes map.
            assert first[4] == {
                "text": "first body",
                "status": "approved",
                "priority": "high",
            }
            # Server defaults carried over for the omitted columns.
            assert second[4] == {
                "text": "",
                "status": "draft",
                "priority": "medium",
            }

            # --- Assert: fixed columns and their checks are gone -------
            with engine.connect() as conn:
                dropped = [
                    row[0]
                    for row in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'work_items' "
                            "AND column_name IN ('text', 'status', 'priority')"
                        )
                    )
                ]
            assert dropped == []

            # --- Assert: built-in type seeded with its attribute set ---
            with engine.connect() as conn:
                type_row = conn.execute(
                    text(
                        "SELECT id, name, id_prefix, is_builtin "
                        "FROM work_item_types"
                    )
                ).one()
                definitions = conn.execute(
                    text(
                        "SELECT key, data_type, default_value "
                        "FROM attribute_definitions ORDER BY position"
                    )
                ).all()

            assert type_row == (1, "requirement", "REQ", True)
            assert [d[0] for d in definitions] == ["text", "status", "priority"]
            assert [d[1] for d in definitions] == ["text", "enum", "enum"]
            assert [d[2] for d in definitions] == ["", "draft", "medium"]

            # --- Assert: the lock survived, retargeted to work_items ---
            with engine.connect() as conn:
                lock = conn.execute(
                    text(
                        "SELECT l.item_id, w.title FROM locks l "
                        "JOIN work_items w ON w.id = l.item_id"
                    )
                ).one()
                old_column = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'locks' AND column_name = 'requirement_id'"
                    )
                ).first()

            assert lock == (1, "legacy one")
            assert old_column is None
        finally:
            engine.dispose()
    finally:
        admin_engine = _admin_engine()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{db_name}"'))
        admin_engine.dispose()


def test_0006_migration_renumbers_duplicate_positions():
    """Applying 0006 to a schema whose types carry duplicate attribute
    positions renumbers only the affected types to a dense 0..n-1 sequence
    in their current display order (position, then id), leaves clean types
    untouched, and installs the (type_id, position) unique constraint that
    rejects further duplicates.
    """
    db_name = f"cronos_mig_{uuid.uuid4().hex[:12]}"
    try:
        admin_engine = _admin_engine()
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        admin_engine.dispose()
    except OperationalError as exc:
        pytest.skip(f"scratch database unavailable: {exc}")

    try:
        engine = create_engine(SCRATCH_URL_TEMPLATE.format(db=db_name))
        try:
            # --- Build the schema through revision 0005 -----------------
            for filename in (
                "0001_initial_baseline.py",
                "0002_users_sessions.py",
                "0003_modules_requirements.py",
                "0004_locks.py",
                "0005_work_items.py",
            ):
                _apply_revision(engine, _load_revision(filename))

            # --- Seed a second type with duplicate positions ------------
            # 0005 already seeds the built-in type (positions 1, 2, 3 —
            # clean). Add a custom type whose attributes repeat position 0.
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO work_item_types "
                        "(id, name, description, id_prefix, is_builtin) "
                        "VALUES (2, 'sw-req', '', 'SW', FALSE)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO attribute_definitions "
                        "(type_id, key, label, data_type, required, position) "
                        "VALUES "
                        "(2, 'description', 'Description', 'text', FALSE, 0), "
                        "(2, 'status', 'Status', 'string', FALSE, 0), "
                        "(2, 'extra', 'Extra', 'string', FALSE, 5)"
                    )
                )

            # --- Apply the migration under test -------------------------
            _apply_revision(engine, _load_revision("0006_unique_attribute_positions.py"))

            with engine.connect() as conn:
                builtin = conn.execute(
                    text(
                        "SELECT position FROM attribute_definitions "
                        "WHERE type_id = 1 ORDER BY position"
                    )
                ).all()
                custom = conn.execute(
                    text(
                        "SELECT key, position FROM attribute_definitions "
                        "WHERE type_id = 2 ORDER BY position"
                    )
                ).all()

            # The clean built-in type is untouched.
            assert [r[0] for r in builtin] == [1, 2, 3]
            # The duplicated positions were renumbered densely in display
            # order (position, then id): 0, 0, 5 -> 0, 1, 2.
            assert custom == [("description", 0), ("status", 1), ("extra", 2)]

            # --- Assert: the unique constraint rejects duplicates -------
            with engine.connect() as conn:
                constraint = conn.execute(
                    text(
                        "SELECT con.conname FROM pg_constraint con "
                        "JOIN pg_class rel ON rel.oid = con.conrelid "
                        "WHERE rel.relname = 'attribute_definitions' "
                        "AND con.contype = 'u'"
                    )
                ).all()
            assert ("uq_attribute_definitions_type_position",) in constraint

            with pytest.raises(Exception, match="uq_attribute_definitions_type_position"):
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO attribute_definitions "
                            "(type_id, key, label, data_type, required, position) "
                            "VALUES (2, 'dupe', 'Dupe', 'string', FALSE, 0)"
                        )
                    )
        finally:
            engine.dispose()
    finally:
        admin_engine = _admin_engine()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{db_name}"'))
        admin_engine.dispose()
