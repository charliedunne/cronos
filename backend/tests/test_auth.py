"""API tests for login, logout, and session validation (task 2.3)."""

import uuid

import pytest

from app.db import SessionLocal
from app.deps import SESSION_COOKIE_NAME
from app.models import User
from app.security import hash_password


@pytest.fixture()
def test_user():
    """Create a temporary user account in the dev database.

    @return A dict with username, password, and id; the account is removed
        (with its sessions via FK cascade) when the test finishes.
    """
    username = f"auth-{uuid.uuid4().hex[:12]}"
    password = "s3cret-password"
    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        yield {"username": username, "password": password, "id": user.id}
        session.query(User).filter(User.id == user.id).delete()
        session.commit()


def test_login_sets_session_cookie(client, test_user) -> None:
    """Successful login returns 200 and sets an httpOnly session cookie."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies

    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    # The session is immediately usable: /me returns this user.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == test_user["username"]


def test_login_rejects_invalid_credentials_without_leaking_detail(
    client, test_user
) -> None:
    """Wrong password and unknown username both yield the same generic 401."""
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"username": test_user["username"], "password": "definitely-wrong"},
    )
    assert wrong_password.status_code == 401
    detail_wrong_password = wrong_password.json()["detail"]

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"username": f"no-such-{uuid.uuid4().hex[:8]}", "password": "whatever"},
    )
    assert unknown_user.status_code == 401
    # Same message: the response does not reveal which part was invalid.
    assert unknown_user.json()["detail"] == detail_wrong_password


def test_request_without_session_is_rejected(client) -> None:
    """A request carrying no session cookie gets a 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_revokes_the_session(client, test_user) -> None:
    """After logout the same cookie is rejected and the cookie is cleared."""
    login = client.post(
        "/api/v1/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    # The cookie is cleared by setting an expired one.
    set_cookie = logout.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "max-age=0" in set_cookie.lower()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
