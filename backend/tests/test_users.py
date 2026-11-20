"""API tests for the admin-only user management endpoints (task 2.4)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import hash_password


def _new_username(prefix: str) -> str:
    """Build a collision-free username for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def admin_client(client):
    """Yield the shared client logged in as a temporary administrator.

    The admin account is created directly in the database (the first admin
    is provisioned out-of-band; see design.md) and removed again on
    teardown, cascading to its sessions via the FK.
    """
    username = _new_username("admin")
    password = "admin-password-1"
    with SessionLocal() as session:
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        admin_id = user.id

    login = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200

    yield client

    with SessionLocal() as session:
        session.query(User).filter(User.id == admin_id).delete()
        session.commit()


@pytest.fixture()
def cleanup_users():
    """Collect user ids created through the API and delete them afterwards."""
    ids: list[int] = []
    yield ids
    with SessionLocal() as session:
        for uid in ids:
            session.query(User).filter(User.id == uid).delete()
        session.commit()


def test_admin_creates_account_and_user_can_log_in(admin_client, cleanup_users):
    """An admin can create an account; the user can log in with it."""
    username = _new_username("newuser")
    password = "brand-new-password"

    response = admin_client.post(
        "/api/v1/users", json={"username": username, "password": password}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == username
    assert body["is_admin"] is False
    cleanup_users.append(body["id"])

    # The new account can authenticate with the given credentials.
    login = admin_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200
    assert login.json()["username"] == username


def test_duplicate_username_is_rejected(admin_client, cleanup_users):
    """Creating a second account with the same username yields 409."""
    username = _new_username("dupuser")
    first = admin_client.post(
        "/api/v1/users", json={"username": username, "password": "pw-one"}
    )
    assert first.status_code == 201
    cleanup_users.append(first.json()["id"])

    second = admin_client.post(
        "/api/v1/users", json={"username": username, "password": "pw-two"}
    )
    assert second.status_code == 409


def test_non_admin_cannot_manage_users(admin_client, cleanup_users):
    """A regular user gets 403 on the account management endpoints."""
    username = _new_username("regular")
    password = "regular-password"
    created = admin_client.post(
        "/api/v1/users", json={"username": username, "password": password}
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    cleanup_users.append(user_id)

    # Log in as the regular user with a separate client (own cookie jar).
    user_client = TestClient(app, base_url="https://testserver")
    login = user_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200

    forbidden_create = user_client.post(
        "/api/v1/users",
        json={"username": _new_username("another"), "password": "pw"},
    )
    assert forbidden_create.status_code == 403

    forbidden_disable = user_client.post(f"/api/v1/users/{user_id}/disable")
    assert forbidden_disable.status_code == 403


def test_disabled_account_cannot_log_in_or_act(admin_client, cleanup_users):
    """Disabling blocks login and existing sessions; re-enabling restores."""
    username = _new_username("toggle")
    password = "toggle-password"
    created = admin_client.post(
        "/api/v1/users", json={"username": username, "password": password}
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    cleanup_users.append(user_id)

    # The new user logs in (separate client: own cookie jar).
    user_client = TestClient(app, base_url="https://testserver")
    login = user_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200
    me_before = user_client.get("/api/v1/auth/me")
    assert me_before.status_code == 200

    # Admin disables the account.
    disabled = admin_client.post(f"/api/v1/users/{user_id}/disable")
    assert disabled.status_code == 200

    # Login is rejected and the existing session no longer works.
    relogin = user_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert relogin.status_code == 401
    me_after = user_client.get("/api/v1/auth/me")
    assert me_after.status_code == 401

    # Re-enabling restores login.
    enabled = admin_client.post(f"/api/v1/users/{user_id}/enable")
    assert enabled.status_code == 200
    final_login = user_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert final_login.status_code == 200


def test_disable_unknown_user_is_404(admin_client):
    """Disabling a non-existent user id yields 404."""
    response = admin_client.post("/api/v1/users/99999999/disable")
    assert response.status_code == 404
