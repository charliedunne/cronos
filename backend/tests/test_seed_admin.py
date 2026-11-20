"""Tests for the out-of-band first-admin seeding CLI (task 2.5)."""

import uuid

import pytest

from app.cli import main as cli_main
from app.db import SessionLocal
from app.models import User


def _new_username(prefix: str) -> str:
    """Build a collision-free username for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def cleanup_users():
    """Collect user ids created through the CLI and delete them afterwards."""
    ids: list[int] = []
    yield ids
    with SessionLocal() as session:
        for uid in ids:
            session.query(User).filter(User.id == uid).delete()
        session.commit()


def test_seed_admin_creates_loginable_admin(client, cleanup_users) -> None:
    """Running seed-admin with provided credentials creates an admin who
    can log in through the API."""
    username = _new_username("seeded")
    password = "seeded-admin-password"

    exit_code = cli_main(
        ["seed-admin", "--username", username, "--password", password]
    )
    assert exit_code == 0

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        assert user is not None
        assert user.is_admin is True
        cleanup_users.append(user.id)

    # The seeded account can authenticate through the real login endpoint.
    login = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200
    assert login.json()["is_admin"] is True


def test_seed_admin_refuses_duplicate_username(client, cleanup_users) -> None:
    """Seeding an already existing username fails and leaves the account
    untouched."""
    username = _new_username("seeddup")
    first = cli_main(
        ["seed-admin", "--username", username, "--password", "first-password"]
    )
    assert first == 0

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        assert user is not None
        original_hash = user.password_hash
        cleanup_users.append(user.id)

    second = cli_main(
        ["seed-admin", "--username", username, "--password", "second-password"]
    )
    assert second == 1

    # The existing account was not modified.
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == username).first()
        assert user.password_hash == original_hash
