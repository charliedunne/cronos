"""Shared pytest fixtures for the backend test suite."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Module, User, WorkItem
from app.security import hash_password


#: Finalizers registered by work-item type factories (see
#: ``test_work_item_types.TypeFactory``); run after every test.
_type_factory_finalizers: list = []


@pytest.fixture(autouse=True)
def _finalize_type_factories():
    """Run registered work-item type factory cleanups after every test.

    Runs last among function-scoped teardowns (it is set up first), so the
    finalizers must not rely on fixture-provided clients being open.
    """
    yield
    for finalize in reversed(_type_factory_finalizers):
        finalize()
    del _type_factory_finalizers[:]


def _login_client(username: str, password: str) -> TestClient:
    """Create a fresh test client logged in with the given credentials.

    @param username Account username.
    @param password Account password.
    @return A new :class:`TestClient` whose cookie jar holds the session.
    """
    new_client = TestClient(app, base_url="https://testserver")
    response = new_client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return new_client


def _cleanup_user_data(user_id: int) -> None:
    """Remove all data owned by a user, in FK-safe order.

    Work items inside the user's modules (regardless of creator), then any
    remaining work items created by the user, then the user's modules, then
    the user itself. Locks cascade from work item deletes.

    @param user_id The id of the user whose data to remove.
    """
    with SessionLocal() as session:
        module_ids = [
            row[0]
            for row in session.query(Module.id).filter(Module.created_by == user_id)
        ]
        if module_ids:
            session.query(WorkItem).filter(
                WorkItem.module_id.in_(module_ids)
            ).delete(synchronize_session=False)
        session.query(WorkItem).filter(
            WorkItem.created_by == user_id
        ).delete(synchronize_session=False)
        session.query(Module).filter(Module.created_by == user_id).delete(
            synchronize_session=False
        )
        session.query(User).filter(User.id == user_id).delete()
        session.commit()


@pytest.fixture()
def client():
    """Yield a test client bound to the application.

    The base URL uses https so that Secure session cookies round-trip
    through the httpx cookie jar (matching production behaviour).
    """
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture()
def user(client):
    """Yield an authenticated regular (non-admin) user.

    Creates a temporary account directly in the database, logs it in
    through the API so that the shared ``client`` acts on its behalf, and
    removes all data owned by the user on teardown.

    @return A dict with the user's id, username, and password.
    """
    username = f"user-{uuid.uuid4().hex[:12]}"
    password = "user-password-1"
    with SessionLocal() as session:
        new_user = User(username=username, password_hash=hash_password(password))
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        user_id = new_user.id

    login = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert login.status_code == 200

    yield {"id": user_id, "username": username, "password": password}

    _cleanup_user_data(user_id)


@pytest.fixture()
def second_user():
    """Yield a second regular user with its own client for two-user
    scenarios (e.g. lock conflicts); cleaned up on teardown.

    @return A dict with the user's id, username, password, and a logged-in
        :class:`TestClient` acting as that user.
    """
    username = f"user2-{uuid.uuid4().hex[:12]}"
    password = "second-user-password"
    with SessionLocal() as session:
        new_user = User(username=username, password_hash=hash_password(password))
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        user_id = new_user.id

    own_client = _login_client(username, password)
    yield {
        "id": user_id,
        "username": username,
        "password": password,
        "client": own_client,
    }
    own_client.close()
    _cleanup_user_data(user_id)


@pytest.fixture()
def admin_client():
    """Yield a temporary administrator account with its own client.

    The first admin is provisioned out-of-band (design.md), so tests that
    need administrative actions create a throwaway admin directly in the
    database; it is removed on teardown.

    @return A dict with the admin's id, username, password, and a logged-in
        :class:`TestClient` acting as that admin.
    """
    username = f"admin-{uuid.uuid4().hex[:12]}"
    password = "admin-password-1"
    with SessionLocal() as session:
        new_admin = User(
            username=username, password_hash=hash_password(password), is_admin=True
        )
        session.add(new_admin)
        session.commit()
        session.refresh(new_admin)
        admin_id = new_admin.id

    own_client = _login_client(username, password)
    yield {"id": admin_id, "username": username, "password": password, "client": own_client}
    own_client.close()
    _cleanup_user_data(admin_id)
