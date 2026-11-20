"""Tests for editing locks (tasks 4.1-4.4)."""

import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Lock, Module, Requirement, User
from app.security import hash_password


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _make_module_and_requirement(client, user_id: int) -> tuple[int, int]:
    """Create a module and one requirement through the API.

    @param client An authenticated test client performing the calls.
    @param user_id The id of the acting user (for cleanup attribution).
    @return A tuple of (module_id, requirement_id).
    """
    module = client.post("/api/v1/modules", json={"name": _new_name("lockmod")})
    assert module.status_code == 201
    module_id = module.json()["id"]

    created = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "lockable"}
    )
    assert created.status_code == 201
    return module_id, created.json()["id"]


def test_second_lock_row_fails_at_database_level():
    """The locks table primary key rejects a second lock for one
    requirement at the database level (task 4.1)."""
    username = _new_name("lockuser")
    module_name = _new_name("lockmodule")

    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password("pw"))
        session.add(user)
        session.commit()
        session.refresh(user)

        module = Module(name=module_name, created_by=user.id)
        session.add(module)
        session.commit()
        session.refresh(module)

        requirement = Requirement(
            module_id=module.id, title="lockable", created_by=user.id
        )
        session.add(requirement)
        session.commit()
        session.refresh(requirement)
        requirement_id = requirement.id

        first = Lock(requirement_id=requirement_id, holder_id=user.id)
        session.add(first)
        session.commit()

        # A second lock row for the same requirement violates the primary
        # key — this is what the API maps to HTTP 409 (design.md D5).
        second = Lock(requirement_id=requirement_id, holder_id=user.id)
        session.add(second)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Cleanup (locks cascade from the requirement delete).
        session.query(Requirement).filter(
            Requirement.id == requirement_id
        ).delete()
        session.query(Module).filter(Module.id == module.id).delete()
        session.query(User).filter(User.id == user.id).delete()
        session.commit()


def test_lock_records_holder_and_second_user_rejected(client, user, second_user):
    """Locking an unlocked requirement records the holder; a second user's
    attempt is rejected with 409 and the original lock is unchanged (4.2)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    locked = client.post(f"/api/v1/requirements/{requirement_id}/lock")
    assert locked.status_code == 200
    assert locked.json()["locked_by"] == user["username"]

    conflict = second_user["client"].post(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert conflict.status_code == 409

    listing = client.get(f"/api/v1/modules/{_module_id(requirement_id)}/requirements")
    entry = next(r for r in listing.json() if r["id"] == requirement_id)
    assert entry["locked_by"] == user["username"]


def _module_id(requirement_id: int) -> int:
    """Find the module containing a requirement via the ORM (test helper).

    @param requirement_id The requirement whose module to look up.
    @return The containing module's id.
    """
    with SessionLocal() as session:
        row = session.get(Requirement, requirement_id)
        return row.module_id


def test_release_unlocks_and_non_holder_cannot_release(client, user, second_user):
    """The holder can release; a non-holder cannot (403); after release any
    authenticated user can lock the requirement (4.2)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    forbidden = second_user["client"].delete(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert forbidden.status_code == 403

    released = client.delete(f"/api/v1/requirements/{requirement_id}/lock")
    assert released.status_code == 204

    # After release, another user can immediately lock it.
    re_locked = second_user["client"].post(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert re_locked.status_code == 200
    assert re_locked.json()["locked_by"] == second_user["username"]


def test_admin_can_force_release_any_lock(client, user, admin_client):
    """An administrator can force-release a lock held by another user; the
    requirement then becomes lockable again (4.2)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    forced = admin_client["client"].post(
        f"/api/v1/requirements/{requirement_id}/force-release"
    )
    assert forced.status_code == 200
    assert forced.json()["locked_by"] is None

    # Force-releasing an already unlocked requirement is rejected.
    again = admin_client["client"].post(
        f"/api/v1/requirements/{requirement_id}/force-release"
    )
    assert again.status_code == 409


def test_update_without_lock_rejected_and_holder_update_retains_lock(client, user):
    """Updates without a lock are rejected; the holder's update succeeds and
    the lock is retained (4.3)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    rejected = client.patch(
        f"/api/v1/requirements/{requirement_id}", json={"title": "nope"}
    )
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    updated = client.patch(
        f"/api/v1/requirements/{requirement_id}",
        json={
            "title": "updated title",
            "text": "updated text",
            "status": "approved",
            "priority": "high",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "updated title"
    assert body["text"] == "updated text"
    assert body["status"] == "approved"
    assert body["priority"] == "high"
    assert body["locked_by"] == user["username"]


def test_non_holder_update_rejected_and_requirement_unchanged(client, user, second_user):
    """A non-holder's update is rejected and the requirement is unchanged
    (4.3)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    rejected = second_user["client"].patch(
        f"/api/v1/requirements/{requirement_id}", json={"title": "hijacked"}
    )
    assert rejected.status_code == 409

    with SessionLocal() as session:
        row = session.get(Requirement, requirement_id)
        assert row.title == "lockable"


def test_holder_deletes_requirement_and_identifier_not_reused(client, user):
    """Deleting without a lock is rejected; the holder's deletion removes the
    requirement and its identifier is never reused (4.3)."""
    module = client.post("/api/v1/modules", json={"name": _new_name("delmod")})
    assert module.status_code == 201
    module_id = module.json()["id"]

    first = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "first"}
    )
    second = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "second"}
    )
    assert first.status_code == 201 and second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]
    first_identifier = first.json()["identifier"]

    # Deleting without holding the lock is rejected.
    rejected = client.delete(f"/api/v1/requirements/{first_id}")
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/requirements/{first_id}/lock").status_code == 200
    deleted = client.delete(f"/api/v1/requirements/{first_id}")
    assert deleted.status_code == 204

    # A new requirement must not reuse the deleted identifier.
    third = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "third"}
    )
    assert third.status_code == 201
    third_body = third.json()
    assert third_body["identifier"] != first_identifier
    assert re.fullmatch(r"REQ-\d{6}", third_body["identifier"])

    listing = client.get(f"/api/v1/modules/{module_id}/requirements")
    identifiers = [r["identifier"] for r in listing.json()]
    assert first_identifier not in identifiers
    assert len(identifiers) == 2
    assert {second_id, third_body["id"]} == {r["id"] for r in listing.json()}


def test_lock_survives_logout(client, user):
    """A lock persists across the holder's logout and re-login; it remains
    releasable by the same user (4.4)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    # Log out: the session is revoked and the cookie cleared.
    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert client.get(f"/api/v1/modules/{_module_id(requirement_id)}/requirements").status_code == 401

    # Log back in as the same user.
    relogin = client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    assert relogin.status_code == 200

    module_id = _module_id(requirement_id)
    listing = client.get(f"/api/v1/modules/{module_id}/requirements")
    entry = next(r for r in listing.json() if r["id"] == requirement_id)
    assert entry["locked_by"] == user["username"]

    # The same user can still release their own lock.
    released = client.delete(f"/api/v1/requirements/{requirement_id}/lock")
    assert released.status_code == 204


def test_lock_visible_to_other_users(client, user, second_user):
    """Another user's module listing shows the lock state and holder (4.4)."""
    _, requirement_id = _make_module_and_requirement(client, user["id"])

    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    module_id = _module_id(requirement_id)
    listing = second_user["client"].get(
        f"/api/v1/modules/{module_id}/requirements"
    )
    assert listing.status_code == 200
    entry = next(r for r in listing.json() if r["id"] == requirement_id)
    assert entry["locked_by"] == user["username"]
